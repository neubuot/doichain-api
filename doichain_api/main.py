"""Doichain REST API.

HTTP-Fassade fuer Doichain Core v31.1.6 auf doi-btc-node: Kette, Bloecke, Transaktionen,
Adressen (ueber den lokalen ElectrumX), Namensoperationen (name_doi, name_show, ...),
Proof of Existence (PoE) und Wallet-Funktionen. Interaktive Doku unter /docs.
"""

import hashlib
import ipaddress
import json
import logging
import re
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import quota
from .auth import LEVELS, auth_level_of, require
from .config import settings
from .electrum import AddressError, ElectrumError, electrum_call, scripthash_for_address
from .rpc import NodeUnavailable, RPCError, rpc

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("doichain_api")

HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HEIGHT_RE = re.compile(r"^[0-9]{1,9}$")
SAT = Decimal("0.00000001")
ENCODINGS = "^(ascii|utf8|hex)$"
# Bloecke kommen im Mittel alle zehn Minuten. Ist der beste Block aelter als das, gilt die Kette als stehend.
MAX_TIP_AGE_SECONDS = 3 * 3600
# Ablauftiefe der Namen, die Doichain Core von Namecoin erbt: Ein Name laeuft so viele Bloecke nach seiner
# letzten Operation ab und kann danach von jedem neu registriert werden.
NAME_EXPIRY_BLOCKS = 36000


# ---------------------------------------------------------------------------
# Fehlerformat (auch in der OpenAPI-Beschreibung)
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    type: str = Field(..., description="rpc, http, validation, node, electrum oder internal")
    code: int = Field(..., description="HTTP-Status oder, bei type=rpc, der Fehlercode der Node")
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


COMMON_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Eingabe fehlerhaft oder von der Node abgelehnt"},
    401: {"model": ErrorResponse, "description": "Schluessel fehlt oder ist ungueltig"},
    402: {"model": ErrorResponse, "description": "Node-Wallet ohne Guthaben (nur schreibende Aufrufe)"},
    403: {"model": ErrorResponse, "description": "Schluesselstufe reicht nicht oder Methode gesperrt"},
    404: {"model": ErrorResponse, "description": "Name, Block, Transaktion oder Pfad nicht vorhanden"},
    405: {"model": ErrorResponse, "description": "HTTP-Methode fuer diesen Pfad nicht erlaubt"},
    409: {"model": ErrorResponse, "description": "Konflikt: schon registriert, fremder Inhaber, wartende oder abgelehnte Operation"},
    413: {"model": ErrorResponse, "description": "Anfrage zu gross (JSON 64 KB, Rohtransaktionen 1 MB, Uploads 50 MB)"},
    422: {"model": ErrorResponse, "description": "JSON-Body oder Parameter passen nicht zum Schema"},
    423: {"model": ErrorResponse, "description": "Wallet gesperrt"},
    429: {"model": ErrorResponse, "description": "Ratenbegrenzung"},
    500: {"model": ErrorResponse, "description": "Interner Fehler der API"},
    502: {"model": ErrorResponse, "description": "Unerwarteter Fehler der Node oder API-Dienst nicht erreichbar"},
    503: {"model": ErrorResponse, "description": "Node oder ElectrumX nicht erreichbar oder noch nicht synchron"},
    504: {"model": ErrorResponse, "description": "Zeitueberschreitung"},
}


# ---------------------------------------------------------------------------
# App-Grundgeruest
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    await rpc.start()
    yield
    await rpc.stop()


DESCRIPTION = """
REST-Schnittstelle zur Doichain-Node **doi-btc-node** (Doichain Core v31.1.6, Kette nach dem
Sicherheits-Fork vom September 2026).

**Stufen:** Lesen ist ohne Schluessel moeglich (sofern `DOI_PUBLIC_READ=true`). Schreibende Aufrufe
(Proof of Existence, `name_doi`, Namensaenderungen, Rohtransaktion senden) brauchen einen
**write**-Schluessel, Wallet-Auszahlungen und der generische RPC-Durchgriff einen **admin**-Schluessel.
Die oeffentliche PoE-Web-App nutzt einen **poe**-Schluessel, der nur Nachweise anlegen darf, mit Tageskontingent
je IP-Adresse und insgesamt (`GET /v1/poe/quota`).
Schluessel oben rechts unter **Authorize** eintragen (`ApiKey` = Header `X-API-Key`) oder als
`Authorization: Bearer <schluessel>` senden.

**Fehlerformat:** `{"error": {"type": "rpc" | "http" | "validation" | "node" | "electrum" | "internal", "code": n, "message": "..."}}`

**Betraege** sind DOI mit acht Nachkommastellen (als Zahl aus der Node, als Zeichenkette bei berechneten Werten).
"""

TAGS = [
    {"name": "Status", "description": "Zustand von Node, Kette und Hilfsdiensten"},
    {"name": "Kette", "description": "Bloecke, Transaktionen, Mempool"},
    {"name": "Adressen", "description": "Guthaben, Historie und UTXOs beliebiger Adressen (ElectrumX)"},
    {"name": "Namen", "description": "Namecoin-artige Namen und die Doichain-Operation name_doi"},
    {"name": "Proof of Existence", "description": "Dokument-Hashes als Namen verankern und pruefen"},
    {"name": "Wallet", "description": "Wallet der Node (nur mit Schluessel)"},
    {"name": "Werkzeuge", "description": "Adresspruefung, Nachrichten signieren, Gebuehren, generischer RPC"},
]

app = FastAPI(
    title="Doichain API",
    version=settings.api_version,
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    responses=COMMON_RESPONSES,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_body(kind: str, code: int, message: str) -> dict:
    return {"error": {"type": kind, "code": code, "message": message}}


@app.exception_handler(RPCError)
async def rpc_error_handler(request: Request, exc: RPCError):
    msg = exc.message
    lowered = msg.lower()
    status = 502
    if exc.code in (-3, -1, -22, -32600, -32602, -32700, -1000):
        status = 400
    elif exc.code == -8:
        status = 404 if "out of range" in lowered else 400
    elif exc.code == -32601:
        status = 404
    elif exc.code == -5:
        status = 404 if any(m in lowered for m in ("not found", "no such", "no information", "not in mempool")) else 400
    elif exc.code == -4:
        if any(m in lowered for m in ("never existed", "not found", "does not exist", "doesn't exist")):
            status = 404
        elif any(m in lowered for m in ("exist", "own", "belong", "registered", "pending")):
            status = 409
        else:
            status = 400
    elif exc.code == -6:
        status = 402
        msg = msg + " (Das Node-Wallet braucht Guthaben, siehe GET /v1/wallet/funding-address)"
    elif exc.code in (-13, -14, -15):
        status = 423
    elif exc.code == -25:
        status = 409 if any(m in lowered for m in ("exists already", "can not be updated", "already being registered", "already active", "pending operations", "already")) else 400
    elif exc.code == -26:
        status = 400
    elif exc.code == -27:
        status = 409
    elif exc.code in (-10, -20, -28):
        status = 503
    if status >= 500:
        logger.warning("%s %s -> RPC-Fehler %s: %s", request.method, request.url.path, exc.code, exc.message)
    return JSONResponse(status_code=status, content=error_body("rpc", exc.code, msg))


@app.exception_handler(NodeUnavailable)
async def node_unavailable_handler(request: Request, exc: NodeUnavailable):
    logger.warning("%s %s -> Node nicht erreichbar: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=503, content=error_body("node", 503, str(exc)))


@app.exception_handler(ElectrumError)
async def electrum_error_handler(request: Request, exc: ElectrumError):
    logger.warning("%s %s -> ElectrumX: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=503, content=error_body("electrum", 503, str(exc)))


@app.exception_handler(AddressError)
async def address_error_handler(_: Request, exc: AddressError):
    return JSONResponse(status_code=400, content=error_body("validation", 400, str(exc)))


@app.exception_handler(quota.QuotaExceeded)
async def quota_handler(request: Request, exc: quota.QuotaExceeded):
    logger.info("PoE-Kontingent erschoepft fuer %s", request.client.host if request.client else "?")
    return JSONResponse(status_code=429, content=error_body("http", 429, str(exc)))


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    """Deckt FastAPIs HTTPException und die 404/405 des Routers ab (Unterklasse beziehungsweise Basisklasse)."""
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)
    if exc.status_code == 404 and detail == "Not Found":
        detail = "Pfad nicht vorhanden, Uebersicht unter /docs"
    if exc.status_code == 405:
        detail = "HTTP-Methode fuer diesen Pfad nicht erlaubt"
    return JSONResponse(status_code=exc.status_code, content=error_body("http", exc.status_code, detail), headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    problems = [f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg')}" for e in exc.errors()]
    return JSONResponse(status_code=422, content=error_body("validation", 422, "; ".join(problems)))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("%s %s -> unerwarteter Fehler", request.method, request.url.path)
    return JSONResponse(status_code=500, content=error_body("internal", 500, "Interner Fehler der API, Details im Journal des Dienstes"))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sats_to_doi(sats: int | None) -> str | None:
    if sats is None:
        return None
    return f"{(Decimal(int(sats)) * SAT).quantize(SAT):.8f}"


def explorer_link(kind: str, value: str) -> str:
    return f"{settings.explorer_url}/{kind}/{value}"


def check_name(name: str) -> str:
    """Namen trimmen, NFC-normalisieren und gegen die Grenzen der Node pruefen."""
    name = unicodedata.normalize("NFC", name.strip())
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")
    if len(name.encode("utf-8")) > settings.max_name_length:
        raise HTTPException(400, f"Name ist laenger als {settings.max_name_length} Byte")
    if any(ord(c) < 32 for c in name):
        raise HTTPException(400, "Name enthaelt Steuerzeichen")
    return name


def check_value(value: str, encoding: str | None) -> str:
    if encoding == "hex":
        try:
            raw = bytes.fromhex(value)
        except ValueError:
            raise HTTPException(400, "value ist kein gueltiger Hex-String")
        length = len(raw)
    else:
        length = len(value.encode("utf-8"))
    if length > settings.max_value_length:
        raise HTTPException(400, f"Wert ist laenger als {settings.max_value_length} Byte")
    return value


def check_hash(value: str) -> str:
    value = value.strip().lower()
    if not HASH_RE.match(value):
        raise HTTPException(400, "hash muss ein SHA-256-Wert mit 64 Hex-Zeichen sein")
    return value


def check_encoding(value: str | None) -> str | None:
    """Leere Zeichenketten (Formulare, Swagger) wie fehlend behandeln, sonst nur ascii, utf8 oder hex."""
    if value is None or value.strip() == "":
        return None
    value = value.strip().lower()
    if value not in ("ascii", "utf8", "hex"):
        raise HTTPException(422, "Kodierung muss ascii, utf8 oder hex sein")
    return value


def blank_to_none(value: str | None) -> str | None:
    return None if value is None or value.strip() == "" else value


def name_options(*, with_value: bool = True, **kwargs: Any) -> dict:
    """Optionsobjekt fuer die Namens-RPCs. Die Node dekodiert standardmaessig ASCII, deshalb
    immer utf8 setzen, sofern der Aufrufer nichts anderes verlangt."""
    opts = {k: v for k, v in kwargs.items() if v is not None}
    opts.setdefault("nameEncoding", "utf8")
    if with_value:
        opts.setdefault("valueEncoding", "utf8")
    return opts


def with_explorer(entry: dict) -> dict:
    if entry.get("txid"):
        entry["explorer_tx"] = explorer_link("tx", entry["txid"])
    return entry


async def name_show_or_none(name: str, value_encoding: str | None = None) -> dict | None:
    try:
        return await rpc.call("name_show", name, name_options(allowExpired=True, valueEncoding=value_encoding))
    except RPCError as exc:
        lowered = exc.message.lower()
        if any(marker in lowered for marker in ("not found", "does not exist", "doesn't exist", "unknown name", "never existed")):
            return None
        raise


def name_ops_of(tx: dict) -> list[dict]:
    ops = []
    for vout in tx.get("vout", []):
        spk = vout.get("scriptPubKey", {})
        name_op = spk.get("nameOp") or vout.get("nameOp")
        if name_op:
            ops.append({"vout": vout.get("n"), "address": spk.get("address"), **name_op})
    return ops


def decorate_tx(tx: dict, block_time: int | None = None, include_hex: bool = True) -> dict:
    tx = dict(tx)
    if block_time is not None and tx.get("blocktime") is None:
        tx["blocktime"] = block_time
    if not include_hex:
        tx.pop("hex", None)
    tx["block_time_iso"] = iso(tx.get("blocktime"))
    tx["name_ops"] = name_ops_of(tx)
    tx["is_name_transaction"] = tx.get("version") == 28928 or bool(tx["name_ops"])
    tx["explorer"] = explorer_link("tx", tx.get("txid", ""))
    return tx


async def ensure_accepted(txid: str) -> dict:
    """name_doi und Co. liefern eine txid auch dann, wenn der Mempool die Transaktion ablehnt
    (CommitTransaction wirft nicht). Deshalb nach jedem Schreibaufruf pruefen und eine abgelehnte
    Transaktion im Wallet verwerfen, damit die Coins nicht gebunden bleiben."""
    try:
        entry = await rpc.call("getmempoolentry", txid)
        fees = entry.get("fees") or {}
        return {"txid": txid, "status": "pending", "in_mempool": True, "fee": fees.get("base"), "vsize": entry.get("vsize"), "explorer": explorer_link("tx", txid)}
    except RPCError as exc:
        if exc.code != -5:
            raise
    tx = await rpc.call("gettransaction", txid, wallet=True)
    if tx.get("confirmations", 0) > 0:
        return {"txid": txid, "status": "confirmed", "in_mempool": False, "explorer": explorer_link("tx", txid)}
    try:
        await rpc.call("abandontransaction", txid, wallet=True)
    except RPCError:
        pass
    logger.warning("Transaktion %s wurde vom Mempool nicht angenommen und im Wallet verworfen", txid)
    raise HTTPException(409, f"Die Node hat die Transaktion {txid} gebaut, der Mempool hat sie aber nicht angenommen (zum Beispiel Name gerade von jemand anderem registriert). Die Transaktion wurde im Wallet verworfen, bitte spaeter erneut versuchen")


async def validated_address(address: str) -> dict:
    validation = await rpc.call("validateaddress", address)
    if not validation.get("isvalid"):
        reason = validation.get("error") or validation.get("error_message") or ""
        raise HTTPException(400, f"Ungueltige Doichain-Adresse ({reason})" if reason else "Ungueltige Doichain-Adresse")
    return validation


async def hash_upload(upload: UploadFile) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(413, f"Datei groesser als {settings.max_upload_bytes} Byte, bitte den Hash lokal berechnen und als JSON senden")
        digest.update(chunk)
    if size == 0:
        raise HTTPException(400, "Leere Datei")
    return digest.hexdigest(), size


def poe_name(hash_hex: str) -> str:
    return settings.poe_prefix + hash_hex


def build_poe_value(hash_hex: str, filename: str | None, note: str | None) -> str:
    """Wert des PoE-Namens. Grenzen: Dateiname 80 Zeichen, Notiz 160 Zeichen, gesamt 520 Byte UTF-8.
    Wird die Bytegrenze durch Mehrbyte-Zeichen ueberschritten, lehnt die API ab statt still zu kuerzen."""
    value: dict[str, Any] = {"v": 1, "alg": "sha256", "hash": hash_hex, "ts": iso(int(time.time()))}
    if filename and filename.strip():
        value["file"] = filename.strip()[:80]
    if note and note.strip():
        value["note"] = note.strip()[:160]
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    size = len(encoded.encode("utf-8"))
    if size > settings.max_value_length:
        raise HTTPException(422, f"Wert des Nachweises waere {size} Byte, erlaubt sind {settings.max_value_length}. Notiz oder Dateiname kuerzen (Umlaute zaehlen zwei Byte)")
    return encoded


def parse_value_json(value: Any) -> dict | None:
    """Namenswert als JSON-Objekt lesen (PoE-Werte sind JSON-Objekte). Andere JSON-Typen und ungueltiges JSON
    ergeben None, damit value_json immer ein Objekt oder null ist."""
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def operation_fields(op: dict, tx: dict) -> dict:
    """Felder einer Namensoperation (Eintrag aus name_show oder name_history) zusammen mit Block und Zeit
    ihrer Transaktion. Alle Felder stammen aus derselben Operation, damit nichts aus zwei Registrierungen
    gemischt wird."""
    value = op.get("value")
    return {
        "txid": op["txid"],
        "height": op.get("height"),
        "block_hash": tx.get("blockhash"),
        "block_time": tx.get("blocktime"),
        "block_time_iso": iso(tx.get("blocktime")),
        "confirmations": tx.get("confirmations", 0),
        "value": value if isinstance(value, str) else None,
        "value_json": parse_value_json(value),
        "owner_address": op.get("address"),
        "explorer_tx": explorer_link("tx", op["txid"]),
    }


def registration_start_index(history: list[dict]) -> int | None:
    """Index des Eintrags in name_history (aelteste Operation zuerst), mit dem die aktuelle Registrierung
    begann, falls sie eine Neuregistrierung nach Ablauf ist. Ein Name laeuft NAME_EXPIRY_BLOCKS nach seiner
    letzten Operation ab. Liegen zwischen zwei Operationen mindestens so viele Bloecke, war der Name dazwischen
    frei und die spaetere Operation ist eine neue Registrierung, moeglicherweise durch jemand anderen.
    Aktualisierungen und Verlaengerungen durch den Inhaber vor dem Ablauf zaehlen nicht. None, wenn der Name
    seit der ersten Registrierung durchgehend gehalten wurde."""
    start = None
    for i in range(1, len(history)):
        previous, current = history[i - 1].get("height"), history[i].get("height")
        if isinstance(previous, int) and isinstance(current, int) and current - previous >= NAME_EXPIRY_BLOCKS:
            start = i
    return start


async def registration_info(name: str, entry: dict, current_tx: dict) -> dict:
    """Erste Verankerung und Beginn der aktuellen Registrierung laut name_history.

    Ein abgelaufener Name kann spaeter erneut registriert werden, auch von jemand anderem. Der Nachweiszeitpunkt
    ist die erste Verankerung, Inhaber und Wert der aktuellen Operation gehoeren dann aber zur spaeteren
    Registrierung. Deshalb beschreibt first_anchored die erste Operation vollstaendig (Block, Zeit, Wert,
    Inhaber), und reregistered_after_expiry sagt, ob die aktuellen Felder aus einer Neuregistrierung stammen.
    Zusaetzliche RPC-Aufrufe: name_history und hoechstens zwei getrawtransaction."""
    current = operation_fields(entry, current_tx)
    try:
        history = await rpc.call("name_history", name, name_options())
    except RPCError:
        # Ohne -namehistory ist nur die aktuelle Operation bekannt. Sie kann auch eine spaetere Registrierung sein,
        # deshalb bleibt der Inhaber der ersten Verankerung unbekannt (null), registrations null zeigt das an.
        return {
            "first_anchored": {**current, "owner_address": None, "registrations": None},
            "reregistered_after_expiry": False,
            "current_registration_start": None,
        }
    history = [h for h in (history or []) if isinstance(h, dict) and h.get("txid")]
    txs: dict[str, dict] = {entry["txid"]: current_tx}

    async def tx_of(txid: str) -> dict:
        if txid not in txs:
            txs[txid] = await rpc.call("getrawtransaction", txid, True)
        return txs[txid]

    first = current
    if history and history[0]["txid"] != entry["txid"]:
        oldest = history[0]
        first = operation_fields(oldest, await tx_of(oldest["txid"]))
    start_index = registration_start_index(history)
    current_start = None
    if start_index is not None:
        start = history[start_index]
        start_tx = await tx_of(start["txid"])
        current_start = {
            "txid": start["txid"],
            "height": start.get("height"),
            "block_time_iso": iso(start_tx.get("blocktime")),
            "explorer_tx": explorer_link("tx", start["txid"]),
        }
    return {
        "first_anchored": {**first, "registrations": len(history) if history else 1},
        "reregistered_after_expiry": start_index is not None,
        "current_registration_start": current_start,
    }


async def poe_status(hash_hex: str) -> dict:
    name = poe_name(hash_hex)
    entry = await name_show_or_none(name)
    pending = await rpc.call("name_pending", name, name_options())
    active = bool(entry) and not entry.get("expired")
    status = "confirmed" if active else ("pending" if pending else ("expired" if entry else "unknown"))
    result: dict[str, Any] = {"hash": hash_hex, "name": name, "exists": entry is not None, "pending": bool(pending), "status": status}
    if entry:
        tx = await rpc.call("getrawtransaction", entry["txid"], True)
        value = entry.get("value")
        registrations = await registration_info(name, entry, tx)
        result.update(
            {
                "txid": entry["txid"],
                "vout": entry.get("vout"),
                "height": entry.get("height"),
                "block_hash": tx.get("blockhash"),
                "block_time": tx.get("blocktime"),
                "block_time_iso": iso(tx.get("blocktime")),
                "confirmations": tx.get("confirmations", 0),
                "owner_address": entry.get("address"),
                "owned_by_this_wallet": entry.get("ismine"),
                "expired": entry.get("expired"),
                "expires_in": entry.get("expires_in"),
                "value": value,
                "value_json": parse_value_json(value),
                "explorer_tx": explorer_link("tx", entry["txid"]),
                **registrations,
            }
        )
    result.setdefault("reregistered_after_expiry", False)
    result.setdefault("current_registration_start", None)
    if pending:
        result["pending_ops"] = [{"txid": p.get("txid"), "op": p.get("op"), "address": p.get("address"), "value": p.get("value"), "explorer_tx": explorer_link("tx", p.get("txid", ""))} for p in pending]
    return result


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------

REANCHOR_DESCRIPTION = (
    "Nur fuer abgelaufene Namen: true registriert den Hash bewusst neu. Der fruehere Nachweis bleibt in der "
    "Kettenhistorie gueltig, die neue Registrierung fuegt nur einen spaeteren Zeitstempel hinzu und ersetzt Notiz "
    "und Inhaber des Namens. Ohne true antwortet die API bei einem abgelaufenen Hash mit 409. Bei aktiven oder "
    "wartenden Nachweisen ohne Wirkung (dort immer 409)."
)

POE_STATUS_DESCRIPTION = (
    "status ist unknown (nie registriert), pending (Operation wartet im Mempool), confirmed (aktiv in der Kette) "
    "oder expired (Registrierung abgelaufen, der Nachweis bleibt in der Kettenhistorie gueltig). "
    "Die Felder auf oberster Ebene (txid, height, block_time, owner_address, value, expires_in) beschreiben die "
    "aktuelle Operation des Namens. first_anchored beschreibt die erste Verankerung vollstaendig mit Block, "
    "Blockhash, Zeit, Wert (value, value_json) und Inhaberadresse (owner_address). Sie ist der eigentliche "
    "Nachweiszeitpunkt. reregistered_after_expiry ist true, wenn der Name nach einem Ablauf neu registriert wurde, "
    "moeglicherweise von jemand anderem. Dann gehoeren Inhaber und Notiz auf oberster Ebene zu dieser spaeteren "
    "Registrierung und nicht zum ersten Verankerer, current_registration_start nennt deren Beginn (txid, height, "
    "block_time_iso, explorer_tx). Aktualisierungen oder Verlaengerungen durch den Inhaber vor dem Ablauf zaehlen "
    "nicht als Neuregistrierung. Ist first_anchored.registrations null, war die Namenshistorie nicht verfuegbar. "
    "Dann beschreibt first_anchored die aktuelle Operation, die auch eine spaetere Registrierung sein kann, "
    "first_anchored.owner_address ist null und reregistered_after_expiry ist false, weil es nicht bestimmbar ist."
)

POE_CREATE_DESCRIPTION = (
    "Verankert poe/<hash> per name_doi mit dem Node-Wallet. Ist der Hash schon aktiv verankert (confirmed) oder "
    "wartet eine Operation im Mempool (pending), antwortet die API mit 409. Ist die Registrierung abgelaufen "
    "(expired), ebenfalls mit 409, denn der fruehere Nachweis bleibt in der Kettenhistorie gueltig und eine neue "
    "Registrierung fuegt nur einen spaeteren Zeitstempel hinzu und ersetzt Notiz und Inhaber des Namens. "
    "Mit reanchor=true wird ein abgelaufener Hash bewusst neu registriert, die Antwort enthaelt dann "
    "reanchored_after_expiry:true und das aeltere Feld renewed mit demselben Wert. Der Nachweiszeitpunkt bleibt "
    "die erste Verankerung (first_anchored in GET /v1/poe/{hash})."
)

class PoeCreate(BaseModel):
    hash: str = Field(..., description="SHA-256 der Datei, 64 Hex-Zeichen", examples=["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"])
    filename: str | None = Field(None, max_length=80, description="Optionaler Dateiname, hoechstens 80 Zeichen (wird oeffentlich im Wert gespeichert)")
    note: str | None = Field(None, max_length=160, description="Optionale Notiz, hoechstens 160 Zeichen (oeffentlich auf der Kette)")
    reanchor: bool = Field(False, description=REANCHOR_DESCRIPTION)


class PoeVerify(BaseModel):
    hash: str = Field(..., description="SHA-256 der Datei, 64 Hex-Zeichen")


class NameDoi(BaseModel):
    name: str = Field(..., description="Name, zum Beispiel poe/<hash> oder id/meinname (bis 255 Byte)")
    value: str = Field("", description="Wert (Text bis 520 Byte oder Hex, siehe value_encoding)")
    dest_address: str | None = Field(None, description="Adresse, die den Namen halten soll (Standard: neue Adresse des Node-Wallets)")
    name_encoding: str | None = Field(None, description="ascii, utf8 (Standard) oder hex, leer = Standard")
    value_encoding: str | None = Field(None, description="ascii, utf8 (Standard) oder hex, leer = Standard")


class NameUpdate(BaseModel):
    name: str = Field(..., description="Name, den das Node-Wallet haelt")
    value: str | None = Field(None, description="Neuer Wert. Weglassen, null oder leere Zeichenkette laesst den Wert unveraendert (einen leeren Wert setzt POST /v1/name/doi mit value \"\")")
    dest_address: str | None = Field(None, description="Neue Inhaberadresse (Uebertragung des Namens)")
    value_encoding: str | None = Field(None, description="ascii, utf8 (Standard) oder hex, leer = Standard")


class NameNew(BaseModel):
    name: str = Field(..., description="Zu reservierender Name (klassische zweistufige Registrierung)")
    dest_address: str | None = Field(None, description="Adresse, die den Namen halten soll")


class NameFirstUpdate(BaseModel):
    name: str = Field(..., description="Name aus name_new")
    rand: str = Field(..., description="Zufallswert aus der Antwort von name_new")
    txid: str = Field(..., description="Transaktions-ID aus der Antwort von name_new")
    value: str = Field("", description="Wert des Namens")
    value_encoding: str | None = Field(None, description="ascii, utf8 (Standard) oder hex, leer = Standard")


class SendToName(BaseModel):
    name: str = Field(..., description="Empfaenger ist der aktuelle Inhaber dieses Namens")
    amount: Decimal = Field(..., gt=0, description="Betrag in DOI")
    comment: str | None = Field(None, description="Nur im Wallet gespeichert, nicht auf der Kette")


class RawTx(BaseModel):
    hex: str = Field(..., description="Serialisierte Transaktion als Hex")


class TxId(BaseModel):
    txid: str = Field(..., min_length=64, max_length=64, description="Transaktions-ID")


class WalletSend(BaseModel):
    address: str = Field(..., description="Zieladresse (N…, 6… oder dc1q…)")
    amount: Decimal = Field(..., gt=0, description="Betrag in DOI")
    comment: str | None = Field(None, description="Nur im Wallet gespeichert")
    subtract_fee_from_amount: bool = Field(False, description="true: Gebuehr vom Betrag abziehen, Empfaenger bekommt weniger")
    fee_rate_sat_vb: int = Field(100, ge=1, le=10000, description="Gebuehrenrate in sat/vB, Standard 100 (siehe GET /v1/fee)")


class NewAddress(BaseModel):
    label: str = Field("", description="Bezeichnung im Wallet")
    address_type: str = Field("bech32", pattern="^(legacy|p2sh-segwit|bech32)$", description="legacy (N…), p2sh-segwit (6…) oder bech32 (dc1q…)")


class MessageVerify(BaseModel):
    address: str = Field(..., description="Adresse, mit der signiert wurde")
    signature: str = Field(..., description="Signatur (Base64)")
    message: str = Field(..., description="Signierter Text")


class MessageSign(BaseModel):
    address: str = Field(..., description="Adresse des Node-Wallets, mit der signiert wird")
    message: str = Field(..., description="Zu signierender Text")


class RpcCall(BaseModel):
    method: str = Field(..., description="RPC-Methode von Doichain Core, zum Beispiel getblockchaininfo")
    params: list[Any] | dict[str, Any] = Field(default_factory=list, description="Positionsparameter als Liste oder benannte Parameter als Objekt")
    wallet: bool = Field(False, description="true, wenn die Methode das Wallet betrifft")


RPC_DENYLIST = {
    # Schluesselmaterial und Wallet-Dateien (auch die neuen Befehle aus Bitcoin Core 28 bis 31)
    "dumpprivkey", "dumpwallet", "importprivkey", "importwallet", "importdescriptors", "importaddress", "importpubkey",
    "importmulti", "importprunedfunds", "sethdseed", "gethdkeys", "derivehdkey", "addhdkey", "createwalletdescriptor",
    "listdescriptors", "encryptwallet", "walletpassphrase", "walletpassphrasechange",
    "createwallet", "restorewallet", "unloadwallet", "loadwallet", "migratewallet", "upgradewallet", "backupwallet",
    "exportwatchonlywallet", "removeprunedfunds", "rescanblockchain", "abortrescan",
    # Node-Steuerung, Netz und Dateien
    "stop", "setnetworkactive", "setban", "clearbanned", "addnode", "disconnectnode", "addpeeraddress", "addconnection",
    "sendmsgtopeer", "invalidateblock", "reconsiderblock", "preciousblock", "dumptxoutset", "loadtxoutset",
    "importmempool", "savemempool", "exportasmap", "logging", "setmocktime", "waitfornewblock", "waitforblock",
    "waitforblockheight", "generate", "generatetoaddress", "generatetodescriptor", "generateblock", "pruneblockchain",
}
# Vorbeugend fuer kuenftige Core-Releases: alles, was nach Export, Import, Dateizugriff oder Schluesselableitung klingt.
RPC_DENY_PREFIXES = ("dump", "import", "export", "backup", "restore", "load", "unload", "generate", "wait", "sethd", "addhd", "derivehd", "gethd", "sendmsg", "encrypt")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Status"], summary="Gesundheitscheck fuer die Ueberwachung (ohne Schluessel)", description="Liefert 200 und ok:true nur, wenn die Node synchron ist, der beste Block juenger als drei Stunden ist, keine Header fehlen und die Fork-Pruefung stimmt. Sonst 503 mit den Gruenden.")
async def health():
    info = await rpc.call("getblockchaininfo")
    header = await rpc.call("getblockheader", info["bestblockhash"])
    problems: list[str] = []
    if info.get("initialblockdownload"):
        problems.append("Node synchronisiert noch (initial block download)")
    lag = int(info.get("headers", 0)) - int(info.get("blocks", 0))
    if lag > 6:
        problems.append(f"{lag} Header voraus, Bloecke fehlen")
    age = int(time.time() - int(header.get("time", 0)))
    if age > MAX_TIP_AGE_SECONDS:
        problems.append(f"letzter Block ist {age // 60} Minuten alt")
    fork_ok: bool | None = None
    if int(info.get("blocks", 0)) >= settings.fork_height:
        fork_ok = (await rpc.call("getblockhash", settings.fork_height)) == settings.fork_hash
        if not fork_ok:
            problems.append("Fork-Pruefung fehlgeschlagen, die Node folgt der falschen Kette")
    body = {
        "ok": not problems,
        "blocks": info["blocks"],
        "headers": info["headers"],
        "synced": not info.get("initialblockdownload"),
        "best_block_age_seconds": age,
        "fork_ok": fork_ok,
        "problems": problems,
    }
    return JSONResponse(status_code=200 if not problems else 503, content=body)


@app.get("/v1/status", tags=["Status"], summary="Gesamtstatus von Node, Kette, Fork-Pruefung, ElectrumX und Wallet", description="Der Wallet-Block mit Guthaben erscheint nur mit write- oder admin-Schluessel, anonyme Aufrufer sehen nur, ob das Wallet Guthaben hat.")
async def status(level: int = Depends(require("read"))):
    chain = await rpc.call("getblockchaininfo")
    net = await rpc.call("getnetworkinfo")
    mem = await rpc.call("getmempoolinfo")
    fork_ok: bool | None = None
    if chain["blocks"] >= settings.fork_height:
        fork_ok = (await rpc.call("getblockhash", settings.fork_height)) == settings.fork_hash
    best_header = await rpc.call("getblockheader", chain["bestblockhash"])
    electrum: dict[str, Any]
    try:
        tip = await electrum_call("blockchain.headers.subscribe", timeout=5.0)
        electrum = {"reachable": True, "height": tip.get("height")}
    except ElectrumError as exc:
        electrum = {"reachable": False, "error": str(exc)}
    wallet: dict[str, Any]
    try:
        balances = await rpc.call("getbalances", wallet=True)
        trusted = balances["mine"]["trusted"]
        if level >= LEVELS["write"]:
            wallet = {"name": settings.rpc_wallet, "balance": trusted, "pending": balances["mine"]["untrusted_pending"]}
        else:
            wallet = {"funded": float(trusted) > 0, "public_poe_available": float(trusted) >= PUBLIC_POE_RESERVE}
    except RPCError as exc:
        wallet = {"error": exc.message}
    return {
        "api_version": settings.api_version,
        "node": {"version": net["version"], "subversion": net["subversion"], "connections": net["connections"]},
        "chain": {
            "name": chain["chain"],
            "blocks": chain["blocks"],
            "headers": chain["headers"],
            "best_block_hash": chain["bestblockhash"],
            "best_block_time": best_header.get("time"),
            "best_block_time_iso": iso(best_header.get("time")),
            "difficulty": chain["difficulty"],
            "initial_block_download": chain["initialblockdownload"],
            "fork_check": {"height": settings.fork_height, "expected": settings.fork_hash, "ok": fork_ok},
        },
        "mempool": {"size": mem["size"], "bytes": mem["bytes"]},
        "electrumx": electrum,
        "wallet": wallet,
        "explorer": settings.explorer_url,
        "public_read": settings.public_read,
        "poe_prefix": settings.poe_prefix,
    }


# ---------------------------------------------------------------------------
# Kette
# ---------------------------------------------------------------------------

@app.get("/v1/chain/info", tags=["Kette"], summary="getblockchaininfo der Node", dependencies=[Depends(require("read"))])
async def chain_info():
    return await rpc.call("getblockchaininfo")


@app.get("/v1/blocks", tags=["Kette"], summary="Die letzten Bloecke (Kopfdaten)", dependencies=[Depends(require("read"))])
async def blocks(
    count: int = Query(10, ge=1, le=50, description="Anzahl Bloecke, hoechstens 50"),
    start: int | None = Query(None, ge=0, description="Hoehe, ab der rueckwaerts gelistet wird (weglassen fuer die Kettenspitze)"),
):
    tip = await rpc.call("getblockcount")
    height = tip if start is None else min(start, tip)
    result = []
    while height >= 0 and len(result) < count:
        block_hash = await rpc.call("getblockhash", height)
        header = await rpc.call("getblockheader", block_hash)
        result.append(
            {
                "height": height,
                "hash": block_hash,
                "time": header.get("time"),
                "time_iso": iso(header.get("time")),
                "n_tx": header.get("nTx"),
                "difficulty": header.get("difficulty"),
                "explorer": explorer_link("block", block_hash),
            }
        )
        height -= 1
    return {"tip": tip, "blocks": result}


@app.get("/v1/block/{block_id}", tags=["Kette"], summary="Block nach Hoehe oder Hash", dependencies=[Depends(require("read"))])
async def block(
    block_id: str = Path(..., description="Blockhoehe (nur Ziffern) oder Blockhash (64 Hex-Zeichen)"),
    verbosity: int = Query(1, ge=1, le=2, description="1 = Transaktions-IDs, 2 = vollstaendige Transaktionen"),
    include_hex: bool = Query(False, description="bei verbosity=2: rohe Transaktionen als Hex mitliefern"),
):
    if HEIGHT_RE.match(block_id):
        block_hash = await rpc.call("getblockhash", int(block_id))
    elif HASH_RE.match(block_id):
        block_hash = block_id.lower()
    else:
        raise HTTPException(400, "block_id muss eine Blockhoehe (Ziffern) oder ein Blockhash (64 Hex-Zeichen) sein")
    data = await rpc.call("getblock", block_hash, verbosity)
    data["time_iso"] = iso(data.get("time"))
    data["explorer"] = explorer_link("block", block_hash)
    if verbosity == 2:
        data["tx"] = [decorate_tx(t, block_time=data.get("time"), include_hex=include_hex) for t in data.get("tx", [])]
    return data


@app.get("/v1/tx/{txid}", tags=["Kette"], summary="Transaktion (dekodiert, mit Namensoperationen)", dependencies=[Depends(require("read"))])
async def transaction(
    txid: str = Path(..., min_length=64, max_length=64, description="Transaktions-ID (64 Hex-Zeichen)"),
    include_hex: bool = Query(False, description="true: rohe Transaktion als Hex mitliefern"),
):
    if not HASH_RE.match(txid):
        raise HTTPException(400, "txid muss aus 64 Hex-Zeichen bestehen")
    tx = await rpc.call("getrawtransaction", txid.lower(), True)
    return decorate_tx(tx, include_hex=include_hex)


@app.post("/v1/tx/decode", tags=["Kette"], summary="Rohtransaktion dekodieren", dependencies=[Depends(require("read"))])
async def tx_decode(body: RawTx):
    return decorate_tx(await rpc.call("decoderawtransaction", body.hex))


@app.post("/v1/tx/send", tags=["Kette"], summary="Signierte Rohtransaktion ins Netz geben (write)", dependencies=[Depends(require("write"))])
async def tx_send(body: RawTx):
    txid = await rpc.call("sendrawtransaction", body.hex)
    return {"txid": txid, "explorer": explorer_link("tx", txid)}


@app.get("/v1/mempool", tags=["Kette"], summary="Mempool-Uebersicht", dependencies=[Depends(require("read"))])
async def mempool(limit: int = Query(100, ge=0, le=1000, description="Anzahl Transaktions-IDs in der Antwort, hoechstens 1000")):
    info = await rpc.call("getmempoolinfo")
    txids = await rpc.call("getrawmempool")
    return {"info": info, "txids": txids[:limit], "total": len(txids)}


# ---------------------------------------------------------------------------
# Adressen (ElectrumX)
# ---------------------------------------------------------------------------

@app.get("/v1/address/{address}", tags=["Adressen"], summary="Guthaben einer Adresse", dependencies=[Depends(require("read"))])
async def address_info(
    address: str = Path(..., description="Doichain-Adresse (N…, 6… oder dc1q…)"),
    with_count: bool = Query(False, description="true: Anzahl Transaktionen mitliefern (laedt die komplette Historie, bei Pool-Adressen mehrere MB)"),
):
    validation = await validated_address(address)
    scripthash = scripthash_for_address(address)
    balance = await electrum_call("blockchain.scripthash.get_balance", scripthash)
    result = {
        "address": address,
        "type": "bech32" if validation.get("iswitness") else ("p2sh" if validation.get("isscript") else "p2pkh"),
        "script_pubkey": validation.get("scriptPubKey"),
        "balance": sats_to_doi(balance.get("confirmed")),
        "unconfirmed": sats_to_doi(balance.get("unconfirmed")),
        "note": "Namens-Outputs (0,01 DOI je Name) zaehlen zum Guthaben, sind aber nur zusammen mit dem Namen ausgebbar und mit dem Ablauf des Namens verloren",
        "explorer": explorer_link("address", address),
    }
    if with_count:
        history = await electrum_call("blockchain.scripthash.get_history", scripthash)
        result["tx_count"] = len(history)
    return result


@app.get("/v1/address/{address}/history", tags=["Adressen"], summary="Transaktionshistorie einer Adresse (neueste zuerst)", description="ElectrumX liefert immer die komplette Historie, limit kuerzt nur die Antwort. Bei Pool- oder Boersenadressen mit Zehntausenden Transaktionen dauert der Aufruf entsprechend.", dependencies=[Depends(require("read"))])
async def address_history(
    address: str = Path(..., description="Doichain-Adresse"),
    limit: int = Query(50, ge=1, le=500, description="Anzahl Eintraege, hoechstens 500"),
    details: bool = Query(False, description="true: die ersten 25 Transaktionen dekodiert mitliefern"),
):
    await validated_address(address)
    scripthash = scripthash_for_address(address)
    history = await electrum_call("blockchain.scripthash.get_history", scripthash)
    total = len(history)
    history = list(reversed(history))[:limit]
    items = []
    for entry in history:
        item = {"txid": entry.get("tx_hash"), "height": entry.get("height"), "confirmed": int(entry.get("height", 0) or 0) > 0, "explorer_tx": explorer_link("tx", entry.get("tx_hash", ""))}
        if details and len(items) < 25:
            item["tx"] = decorate_tx(await rpc.call("getrawtransaction", entry["tx_hash"], True))
        items.append(item)
    return {"address": address, "total": total, "count": len(items), "history": items}


@app.get("/v1/address/{address}/utxos", tags=["Adressen"], summary="Unverbrauchte Outputs einer Adresse", dependencies=[Depends(require("read"))])
async def address_utxos(
    address: str = Path(..., description="Doichain-Adresse"),
    limit: int = Query(500, ge=1, le=5000, description="Anzahl Outputs in der Antwort, hoechstens 5000"),
    offset: int = Query(0, ge=0, description="Anzahl zu ueberspringender Outputs (Blaettern)"),
):
    await validated_address(address)
    scripthash = scripthash_for_address(address)
    utxos = await electrum_call("blockchain.scripthash.listunspent", scripthash)
    page = utxos[offset:offset + limit]
    return {
        "address": address,
        "total": len(utxos),
        "count": len(page),
        "offset": offset,
        "utxos": [{"txid": u.get("tx_hash"), "vout": u.get("tx_pos"), "height": u.get("height"), "value": sats_to_doi(u.get("value"))} for u in page],
        "total_value": sats_to_doi(sum(int(u.get("value", 0)) for u in utxos)),
    }


# ---------------------------------------------------------------------------
# Namen
# ---------------------------------------------------------------------------

@app.get("/v1/names", tags=["Namen"], summary="Namen durchsuchen (name_scan) mit Blaettern", description="Liefert bis zu count Namen. Die Node sortiert erst nach Namenslaenge, dann nach Bytewert, start (einschliesslich) und after (ausschliesslich) sind Cursor in dieser Reihenfolge, zum Filtern prefix verwenden. Abgelaufene Namen werden standardmaessig uebersprungen, dafuer liest die API bis zu 5000 Eintraege je Aufruf. Zum Weiterblaettern next_after als after uebergeben, bis exhausted true ist. regexp braucht einen write-Schluessel (Backtracking-Ausdruecke koennen die Node lange beschaeftigen).", dependencies=[Depends(require("read"))])
async def names_scan(
    level: int = Depends(require("read")),
    prefix: str | None = Query(None, description="Nur Namen mit diesem Praefix, zum Beispiel poe/ oder e/"),
    start: str = Query("", description="Cursor: ab diesem Namen (einschliesslich) in der Reihenfolge der Node (Laenge, dann Bytewert)"),
    after: str | None = Query(None, description="Cursor: nach diesem Namen (ausschliesslich) weiterblaettern, ersetzt start. Wert aus next_after uebernehmen"),
    count: int = Query(100, ge=1, le=500, description="Gewuenschte Anzahl Treffer, hoechstens 500"),
    regexp: str | None = Query(None, max_length=64, description="Regulaerer Ausdruck auf den Namen (nur mit write-Schluessel, hoechstens 64 Zeichen)"),
    min_conf: int = Query(1, ge=1, description="Mindestbestaetigungen der letzten Operation"),
    include_expired: bool = Query(False, description="true: abgelaufene Namen mitliefern"),
    value_encoding: str | None = Query(None, description="ascii, utf8 (Standard) oder hex"),
):
    prefix, after, regexp = blank_to_none(prefix), blank_to_none(after), blank_to_none(regexp)
    if regexp is not None and level < LEVELS["write"]:
        raise HTTPException(403, "regexp ist nur mit write-Schluessel erlaubt, ohne Schluessel bitte prefix verwenden")
    options = name_options(prefix=prefix, regexp=regexp, minConf=min_conf, valueEncoding=check_encoding(value_encoding))
    cursor = after if after else start
    skip_cursor = bool(after)
    collected: list[dict] = []
    scanned = 0
    exhausted = False
    last_scanned: str | None = None
    page_size = 500
    while len(collected) < count and scanned < 5000:
        page = await rpc.call("name_scan", cursor, page_size, options)
        if not page:
            exhausted = True
            break
        for entry in page:
            name = entry.get("name")
            scanned += 1
            last_scanned = name
            if skip_cursor and name == cursor:
                continue
            if not include_expired and entry.get("expired"):
                continue
            collected.append(with_explorer(entry))
            if len(collected) >= count:
                break
        if len(page) < page_size:
            exhausted = len(collected) < count
            break
        if last_scanned == cursor:
            exhausted = True
            break
        cursor = last_scanned
        skip_cursor = True
    return {
        "count": len(collected),
        "scanned": scanned,
        "exhausted": exhausted,
        "next_after": None if exhausted else last_scanned,
        "names": collected,
    }


@app.get("/v1/names/pending", tags=["Namen"], summary="Unbestaetigte Namensoperationen im Mempool", dependencies=[Depends(require("read"))])
async def names_pending(name: str | None = Query(None, description="Nur Operationen auf diesen Namen")):
    result = await rpc.call("name_pending", name if name else None, name_options())
    return {"count": len(result), "pending": [with_explorer(r) for r in result]}


@app.get("/v1/name/{name:path}/history", tags=["Namen"], summary="Vollstaendige Historie eines Namens", dependencies=[Depends(require("read"))])
async def name_history(
    name: str = Path(..., description="Name, Schraegstriche erlaubt (poe/…, e/…)"),
    value_encoding: str | None = Query(None, description="ascii, utf8 (Standard) oder hex"),
):
    name = check_name(name)
    history = await rpc.call("name_history", name, name_options(valueEncoding=check_encoding(value_encoding)))
    return {"name": name, "count": len(history), "history": [with_explorer(h) for h in history]}


@app.get("/v1/name/{name:path}", tags=["Namen"], summary="Aktuellen Wert eines Namens lesen (name_show)", description="Abgelaufene Namen kommen mit 200 und expired:true (negatives expires_in), unbekannte mit 404. pending:true zeigt eine wartende Operation im Mempool, auch bei bestehenden Namen (Erneuerung, Aktualisierung). Namen, die auf /history enden oder . und .. als Pfadsegment enthalten, sind im Pfad mehrdeutig, dafuer GET /v1/name?name=... verwenden.", dependencies=[Depends(require("read"))])
async def name_show(
    name: str = Path(..., description="Name, Schraegstriche erlaubt (poe/…, e/…)"),
    value_encoding: str | None = Query(None, description="ascii, utf8 (Standard) oder hex"),
):
    name = check_name(name)
    entry = await name_show_or_none(name, check_encoding(value_encoding))
    pending = await rpc.call("name_pending", name, name_options())
    if entry is None:
        if pending:
            return {"name": name, "exists": False, "pending": True, "pending_ops": [with_explorer(p) for p in pending]}
        raise HTTPException(404, f"Name '{name}' ist nicht registriert")
    entry["exists"] = True
    entry["pending"] = bool(pending)
    if pending:
        entry["pending_ops"] = [with_explorer(p) for p in pending]
    return with_explorer(entry)


@app.get("/v1/name", tags=["Namen"], summary="Namen per Query-Parameter lesen (eindeutig fuer jeden Namen)", description="Wie GET /v1/name/{name}, der Name steht aber im Query-Parameter name. Empfohlen fuer Programme, weil Namen mit /history am Ende oder Punkt-Segmenten im Pfad mehrdeutig sind.", dependencies=[Depends(require("read"))])
async def name_show_query(
    name: str = Query(..., min_length=1, max_length=1024, description="Name, zum Beispiel poe/<hash> oder d/beispiel"),
    value_encoding: str | None = Query(None, description="ascii, utf8 (Standard) oder hex"),
):
    return await name_show(name=name, value_encoding=value_encoding)


@app.get("/v1/names/history", tags=["Namen"], summary="Historie eines Namens per Query-Parameter (eindeutig fuer jeden Namen)", dependencies=[Depends(require("read"))])
async def name_history_query(
    name: str = Query(..., min_length=1, max_length=1024, description="Name, zum Beispiel poe/<hash> oder d/beispiel"),
    value_encoding: str | None = Query(None, description="ascii, utf8 (Standard) oder hex"),
):
    return await name_history(name=name, value_encoding=value_encoding)


@app.post("/v1/name/doi", tags=["Namen"], summary="Namen per name_doi registrieren, aktualisieren oder verlaengern (write)", description="Ein freier oder abgelaufener Name wird registriert, ein eigener aktiver Name aktualisiert (das verlaengert den Ablauf um 36.000 Bloecke). Je Name ist nur eine unbestaetigte Operation erlaubt.", dependencies=[Depends(require("write"))])
async def name_doi(body: NameDoi):
    name = check_name(body.name)
    value = check_value(body.value, body.value_encoding)
    options = name_options(destAddress=blank_to_none(body.dest_address), nameEncoding=check_encoding(body.name_encoding), valueEncoding=check_encoding(body.value_encoding))
    txid = await rpc.call("name_doi", name, value, options, wallet=True)
    result = await ensure_accepted(txid)
    result["name"] = name
    return result


@app.post("/v1/name/update", tags=["Namen"], summary="Namen aendern oder uebertragen (name_update, write)", dependencies=[Depends(require("write"))])
async def name_update(body: NameUpdate):
    name = check_name(body.name)
    options = name_options(destAddress=blank_to_none(body.dest_address), valueEncoding=check_encoding(body.value_encoding))
    value = check_value(body.value, body.value_encoding) if body.value else None
    if value is None and not options.get("destAddress"):
        raise HTTPException(422, "Entweder value oder dest_address angeben, sonst gibt es nichts zu aendern")
    txid = await rpc.call("name_update", name, value, options, wallet=True)
    result = await ensure_accepted(txid)
    result["name"] = name
    return result


@app.post("/v1/name/new", tags=["Namen"], summary="Schritt 1 der klassischen Registrierung (name_new, write)", dependencies=[Depends(require("write"))])
async def name_new(body: NameNew):
    name = check_name(body.name)
    result = await rpc.call("name_new", name, name_options(with_value=False, destAddress=body.dest_address), wallet=True)
    accepted = await ensure_accepted(result[0])
    return {"name": name, "txid": result[0], "rand": result[1], "status": accepted["status"], "explorer": accepted["explorer"], "hint": "Nach 12 Bestaetigungen mit POST /v1/name/firstupdate abschliessen"}


@app.post("/v1/name/firstupdate", tags=["Namen"], summary="Schritt 2 der klassischen Registrierung (name_firstupdate, write)", dependencies=[Depends(require("write"))])
async def name_firstupdate(body: NameFirstUpdate):
    name = check_name(body.name)
    value = check_value(body.value, body.value_encoding)
    txid = await rpc.call("name_firstupdate", name, body.rand, body.txid, value, name_options(valueEncoding=check_encoding(body.value_encoding)), wallet=True)
    result = await ensure_accepted(txid)
    result["name"] = name
    return result


@app.post("/v1/name/sendtoname", tags=["Namen"], summary="DOI an den Inhaber eines Namens senden (admin)", dependencies=[Depends(require("admin"))])
async def send_to_name(body: SendToName):
    name = check_name(body.name)
    txid = await rpc.call("sendtoname", name, str(body.amount), body.comment or "", wallet=True)
    result = await ensure_accepted(txid)
    result["name"] = name
    return result


# ---------------------------------------------------------------------------
# Proof of Existence
# ---------------------------------------------------------------------------

def client_ip(request: Request) -> str:
    """Client-Adresse fuer das Kontingent. IPv6 wird auf das /64-Praefix zusammengefasst, weil ein Anschluss
    dort beliebig viele Einzeladressen hat. IPv4-gemappte IPv6-Adressen (::ffff:a.b.c.d, etwa von einem
    Dual-Stack-Socket) zaehlen als die enthaltene IPv4-Adresse, sonst teilten sich alle IPv4-Clients ein
    einziges /64-Kontingent."""
    host = request.client.host if request.client else "unbekannt"
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network((addr.packed, 64), strict=False).network_address) + "/64"
    return str(addr)


# Unter dieser Reserve (DOI, bestaetigt) pausieren die oeffentlichen Nachweise mit poe-Schluessel.
PUBLIC_POE_RESERVE = 5.0


async def public_poe_guard() -> None:
    """Oeffentliche Nachweise nur, solange das Wallet eine Reserve behaelt."""
    try:
        balances = await rpc.call("getbalances", wallet=True)
        if float(balances["mine"]["trusted"]) < PUBLIC_POE_RESERVE:
            raise HTTPException(503, "Die oeffentliche Nachweis-App ist vorerst pausiert, das Betriebsguthaben ist aufgebraucht. Mit eigenem write-Schluessel weiterhin moeglich")
    except RPCError:
        pass


@app.get("/v1/poe/quota", tags=["Proof of Existence"], summary="Verbleibendes Tageskontingent der oeffentlichen PoE-App (poe-Schluessel)", description="Mit write- oder admin-Schluessel gibt es kein Kontingent, dann steht unlimited:true.")
async def poe_quota(request: Request, level: int = Depends(require("poe"))):
    if level > LEVELS["poe"]:
        return {"unlimited": True}
    return {"unlimited": False, **quota.usage(client_ip(request))}


@app.post("/v1/poe/verify", tags=["Proof of Existence"], summary="Nachweis pruefen (Hash als JSON)", description="Antwort wie GET /v1/poe/{hash}. " + POE_STATUS_DESCRIPTION, dependencies=[Depends(require("read"))])
async def poe_verify(body: PoeVerify):
    return await poe_status(check_hash(body.hash))


@app.post("/v1/poe/verify/file", tags=["Proof of Existence"], summary="Nachweis pruefen (Datei hochladen, Hash wird hier berechnet)", description="Antwort wie GET /v1/poe/{hash}, ergaenzt um file (Name und Groesse). " + POE_STATUS_DESCRIPTION, dependencies=[Depends(require("read"))])
async def poe_verify_file(file: UploadFile = File(..., description="Datei bis 50 MB, verlaesst den Server nicht")):
    hash_hex, size = await hash_upload(file)
    result = await poe_status(hash_hex)
    result["file"] = {"name": file.filename, "size": size}
    return result


# --- Oeffentlicher PoE-Endpunkt ohne API-Key ---

class PoePublicCreate(BaseModel):
    hash: str = Field(..., description="SHA-256 der Datei, 64 Hex-Zeichen", examples=["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"])
    filename: str | None = Field(None, max_length=80, description="Optionaler Dateiname, hoechstens 80 Zeichen (wird oeffentlich im Wert gespeichert)")
    note: str | None = Field(None, max_length=160, description="Optionale Notiz, hoechstens 160 Zeichen (oeffentlich auf der Kette)")


@app.get("/v1/poe/public/quota", tags=["Proof of Existence"], summary="Verbleibendes Tageskontingent des oeffentlichen Endpunkts (ohne Schluessel)")
async def poe_public_quota(request: Request):
    return {"unlimited": False, **quota.usage(client_ip(request), per_ip_day=settings.poe_nokey_per_ip_day, per_day=settings.poe_nokey_per_day)}


@app.post("/v1/poe/public", tags=["Proof of Existence"], summary="Nachweis anlegen ohne API-Key (IP-basiertes Tageskontingent)", description="Oeffentlicher Endpunkt ohne Authentifizierung. Kontingent je IP-Adresse und Tag, Standardmaessig 3 je IP und 50 insgesamt. Neuregistrierung (reanchor) ist hier nicht moeglich.", status_code=201)
async def poe_public_create(body: PoePublicCreate, request: Request):
    return await _poe_create(check_hash(body.hash), body.filename, body.note, public=True, ip=client_ip(request), reanchor=False, nokey=True)


# {hash} muss nach den /v1/poe/public/* und /v1/poe/quota Routen stehen, damit FastAPI sie nicht als Hash-Parameter deutet.
@app.get("/v1/poe/{hash}", tags=["Proof of Existence"], summary="Nachweis zu einem SHA-256-Hash pruefen", description=POE_STATUS_DESCRIPTION, dependencies=[Depends(require("read"))])
async def poe_get(hash: str = Path(..., description="SHA-256 der Datei, 64 Hex-Zeichen")):
    return await poe_status(check_hash(hash))


@app.post("/v1/poe", tags=["Proof of Existence"], summary="Nachweis anlegen (Hash als JSON, poe oder write)", description=POE_CREATE_DESCRIPTION, status_code=201)
async def poe_create(body: PoeCreate, request: Request, level: int = Depends(require("poe"))):
    return await _poe_create(check_hash(body.hash), body.filename, body.note, public=(level == LEVELS["poe"]), ip=client_ip(request), reanchor=body.reanchor)


@app.post("/v1/poe/file", tags=["Proof of Existence"], summary="Nachweis anlegen (Datei hochladen, poe oder write)", description=POE_CREATE_DESCRIPTION + " reanchor ist hier ein Formularfeld (true oder false).", status_code=201)
async def poe_create_file(
    request: Request,
    file: UploadFile = File(..., description="Datei bis 50 MB, nur der Hash geht auf die Kette"),
    note: str | None = Form(None, max_length=160, description="Optionale Notiz, hoechstens 160 Zeichen (oeffentlich)"),
    reanchor: bool = Form(False, description=REANCHOR_DESCRIPTION),
    level: int = Depends(require("poe")),
):
    hash_hex, size = await hash_upload(file)
    result = await _poe_create(hash_hex, file.filename, note, public=(level == LEVELS["poe"]), ip=client_ip(request), reanchor=reanchor)
    result["file"] = {"name": file.filename, "size": size}
    return result


async def _poe_create(hash_hex: str, filename: str | None, note: str | None, *, public: bool = False, ip: str = "", reanchor: bool = False, nokey: bool = False) -> dict:
    current = await poe_status(hash_hex)
    if current["status"] == "confirmed":
        # Block und Zeit der ersten Verankerung nennen, nicht die einer spaeteren Neuregistrierung.
        first = current.get("first_anchored") or {}
        raise HTTPException(
            409,
            f"Fuer diesen Hash existiert bereits ein Nachweis (erste Verankerung in Block {first.get('height') or current.get('height')}, "
            f"{first.get('block_time_iso') or current.get('block_time_iso')}), siehe GET /v1/poe/{hash_hex}",
        )
    if current["pending"]:
        raise HTTPException(409, "Fuer diesen Hash wartet bereits eine unbestaetigte Namensoperation im Mempool")
    expired = current["status"] == "expired"
    if expired and not reanchor:
        # Kein stilles Neuregistrieren: Die neue Registrierung wuerde Notiz und Inhaber des Namens ersetzen,
        # waehrend der Nachweiszeitpunkt die erste Verankerung bleibt.
        first = current.get("first_anchored") or {}
        raise HTTPException(
            409,
            f"Der Name fuer diesen Hash ist abgelaufen, der fruehere Nachweis bleibt aber in der Kettenhistorie gueltig "
            f"(erste Verankerung in Block {first.get('height')}, {first.get('block_time_iso')}). "
            "Eine neue Registrierung fuegt nur einen spaeteren Zeitstempel hinzu und ersetzt Notiz und Inhaber des Namens. "
            f"Wer das bewusst will, sendet reanchor=true. Details unter GET /v1/poe/{hash_hex}",
        )
    name = poe_name(hash_hex)
    value = build_poe_value(hash_hex, filename, note)
    # Kontingentgrenzen: nokey (oeffentlich ohne Schluessel) nutzt engere Grenzen als poe-Schluessel.
    quota_limits = {}
    if nokey:
        quota_limits = {"per_ip_day": settings.poe_nokey_per_ip_day, "per_day": settings.poe_nokey_per_day}
    remaining = None
    if public:
        await public_poe_guard()
        remaining = quota.register(ip, **quota_limits)
    try:
        txid = await rpc.call("name_doi", name, value, name_options(), wallet=True)
        result = await ensure_accepted(txid)
    except Exception:
        if public:
            quota.release(ip)
            remaining = quota.usage(ip, **quota_limits)
        raise
    result.update(
        {
            "hash": hash_hex,
            "name": name,
            "value": value,
            "reanchored_after_expiry": expired,
            # renewed: aelterer Name desselben Feldes, bleibt fuer bestehende Clients erhalten.
            "renewed": expired,
            "hint": "Nach der ersten Bestaetigung (im Mittel 10 Minuten) liefert GET /v1/poe/<hash> Blockhoehe und Zeitstempel. Erst dann ist der Nachweis endgueltig",
        }
    )
    if remaining is not None:
        result["quota"] = remaining
    return result


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

@app.get("/v1/wallet", tags=["Wallet"], summary="Wallet-Zustand und Guthaben (write)", dependencies=[Depends(require("write"))])
async def wallet_info():
    info = await rpc.call("getwalletinfo", wallet=True)
    balances = await rpc.call("getbalances", wallet=True)
    names = await rpc.call("name_list", None, name_options(), wallet=True)
    return {
        "name": info.get("walletname"),
        "balance": balances["mine"]["trusted"],
        "pending": balances["mine"]["untrusted_pending"],
        "immature": balances["mine"]["immature"],
        "tx_count": info.get("txcount"),
        "encrypted": "unlocked_until" in info,
        "names_owned": len(names),
        "last_processed_block": info.get("lastprocessedblock"),
    }


@app.get("/v1/wallet/funding-address", tags=["Wallet"], summary="Einzahlungsadresse, um das Wallet mit DOI fuer Gebuehren und die 0,01 DOI je Name zu versorgen", dependencies=[Depends(require("read"))])
async def wallet_funding_address():
    addresses: dict = {}
    try:
        addresses = await rpc.call("getaddressesbylabel", "api-funding", wallet=True)
    except RPCError as exc:
        if exc.code != -11 and "No addresses" not in exc.message:
            raise
    if not addresses:
        raise HTTPException(503, "Einzahlungsadresse ist nicht eingerichtet (Label api-funding fehlt im Wallet), bitte deploy/install.sh ausfuehren")
    address = sorted(addresses.keys())[0]
    return {"address": address, "hint": "Jeder Name bindet 0,01 DOI (kein Pfand, mit dem Ablauf des Namens verloren), jede Namensoperation kostet rund 0,0002 bis 0,0005 DOI Gebuehr", "explorer": explorer_link("address", address)}


@app.get("/v1/wallet/names", tags=["Wallet"], summary="Namen, die das Wallet haelt (name_list, write)", dependencies=[Depends(require("write"))])
async def wallet_names():
    names = await rpc.call("name_list", None, name_options(), wallet=True)
    return {"count": len(names), "names": [with_explorer(n) for n in names]}


@app.post("/v1/wallet/address", tags=["Wallet"], summary="Neue Empfangsadresse erzeugen (write)", dependencies=[Depends(require("write"))])
async def wallet_new_address(body: NewAddress):
    address = await rpc.call("getnewaddress", body.label, body.address_type, wallet=True)
    return {"address": address, "label": body.label, "type": body.address_type, "explorer": explorer_link("address", address)}


@app.get("/v1/wallet/transactions", tags=["Wallet"], summary="Letzte Wallet-Transaktionen (write)", dependencies=[Depends(require("write"))])
async def wallet_transactions(count: int = Query(25, ge=1, le=200, description="Anzahl, hoechstens 200")):
    txs = await rpc.call("listtransactions", "*", count, wallet=True)
    return {"count": len(txs), "transactions": list(reversed(txs))}


@app.get("/v1/wallet/utxos", tags=["Wallet"], summary="Unverbrauchte Outputs des Wallets (write)", dependencies=[Depends(require("write"))])
async def wallet_utxos(min_conf: int = Query(0, ge=0, description="Mindestbestaetigungen")):
    utxos = await rpc.call("listunspent", min_conf, wallet=True)
    return {"count": len(utxos), "utxos": utxos}


@app.post("/v1/wallet/abandon", tags=["Wallet"], summary="Unbestaetigte, nicht mehr weiterleitbare Wallet-Transaktion verwerfen (write)", description="Gibt die gebundenen Coins einer Transaktion frei, die nicht mehr im Mempool ist und nie bestaetigt wird (zum Beispiel ein verlorener Wettlauf um einen Namen).", dependencies=[Depends(require("write"))])
async def wallet_abandon(body: TxId):
    await rpc.call("abandontransaction", body.txid, wallet=True)
    return {"txid": body.txid, "abandoned": True}


@app.post("/v1/wallet/send", tags=["Wallet"], summary="DOI an eine Adresse senden (admin)", dependencies=[Depends(require("admin"))])
async def wallet_send(body: WalletSend):
    await validated_address(body.address)
    params = {
        "address": body.address,
        "amount": str(body.amount),
        "comment": body.comment or "",
        "subtractfeefromamount": body.subtract_fee_from_amount,
        "fee_rate": body.fee_rate_sat_vb,
    }
    txid = await rpc.call("sendtoaddress", named=params, wallet=True)
    result = await ensure_accepted(txid)
    result["address"] = body.address
    result["amount"] = str(body.amount)
    return result


# ---------------------------------------------------------------------------
# Werkzeuge
# ---------------------------------------------------------------------------

@app.get("/v1/validate/{address}", tags=["Werkzeuge"], summary="Adresse pruefen", dependencies=[Depends(require("read"))])
async def validate(address: str = Path(..., description="Zu pruefende Adresse")):
    return await rpc.call("validateaddress", address)


@app.post("/v1/message/verify", tags=["Werkzeuge"], summary="Signierte Nachricht pruefen", dependencies=[Depends(require("read"))])
async def message_verify(body: MessageVerify):
    ok = await rpc.call("verifymessage", body.address, body.signature, body.message)
    return {"valid": bool(ok), "address": body.address}


@app.post("/v1/message/sign", tags=["Werkzeuge"], summary="Nachricht mit einer Wallet-Adresse signieren (admin)", dependencies=[Depends(require("admin"))])
async def message_sign(body: MessageSign):
    signature = await rpc.call("signmessage", body.address, body.message, wallet=True)
    return {"address": body.address, "signature": signature}


@app.get("/v1/fee", tags=["Werkzeuge"], summary="Gebuehrenempfehlung (es gibt keinen Gebuehrenmarkt)", dependencies=[Depends(require("read"))])
async def fee():
    estimate = await rpc.call("estimatesmartfee", 6)
    return {
        "recommended_fee_rate_sat_vb": 100,
        "recommended_doi_per_kvb": "0.001",
        "typical_tx_cost_doi": "0.0002 bis 0.0005",
        "name_deposit_doi": "0.01",
        "estimatesmartfee": estimate,
        "note": "estimatesmartfee liefert auf Doichain keine Schaetzung. 100 sat/vB (0,001 DOI/kvB) entspricht der minrelaytxfee unveraenderter Nodes und wird im naechsten Block aufgenommen.",
    }


@app.get("/v1/network", tags=["Werkzeuge"], summary="Netzwerk und Peers", dependencies=[Depends(require("read"))])
async def network():
    net = await rpc.call("getnetworkinfo")
    peers = await rpc.call("getpeerinfo")
    return {
        "version": net.get("version"),
        "subversion": net.get("subversion"),
        "protocol_version": net.get("protocolversion"),
        "connections": net.get("connections"),
        "connections_in": net.get("connections_in"),
        "connections_out": net.get("connections_out"),
        "peers": [{"addr": p.get("addr"), "subver": p.get("subver"), "inbound": p.get("inbound"), "synced_blocks": p.get("synced_blocks")} for p in peers],
    }


@app.post("/v1/rpc", tags=["Werkzeuge"], summary="Generischer RPC-Durchgriff auf die Node (admin)", description="Ruft jede RPC-Methode von Doichain Core auf, ausser den gesperrten (Schluesselmaterial, Wallet-Dateien, Node-Steuerung, Dateizugriff). params als Liste (Positionsparameter) oder Objekt (benannte Parameter).", dependencies=[Depends(require("admin"))])
async def generic_rpc(body: RpcCall):
    method = body.method.strip().lower()
    if not re.fullmatch(r"[a-z_0-9]+", method):
        raise HTTPException(400, "Ungueltiger Methodenname")
    if method in RPC_DENYLIST or method.startswith(RPC_DENY_PREFIXES):
        raise HTTPException(403, f"Methode '{method}' ist ueber die API gesperrt (Schluesselmaterial, Wallet-Dateien, Dateizugriff oder Node-Steuerung)")
    if isinstance(body.params, dict):
        result = await rpc.call(method, named=body.params, wallet=body.wallet)
    else:
        result = await rpc.call(method, *body.params, wallet=body.wallet)
    return {"method": method, "result": result}


# ---------------------------------------------------------------------------
# OpenAPI: oeffentlich lesbare Routen kenntlich machen
# ---------------------------------------------------------------------------

def _auth_levels(dependant: Any) -> set[str]:
    """Alle mit require() erzeugten Stufen in einem Dependency-Baum."""
    levels: set[str] = set()
    for dep in getattr(dependant, "dependencies", []) or []:
        level = auth_level_of(dep.call)
        if level:
            levels.add(level)
        levels |= _auth_levels(dep)
    return levels


def public_read_operations() -> set[tuple[str, str]]:
    """(Pfad, Methode) aller Routen im Schema, deren staerkste Schluesselpruefung require("read") ist."""
    operations: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        levels = _auth_levels(route.dependant)
        if levels and max(LEVELS[level] for level in levels) == LEVELS["read"]:
            for method in route.methods or ():
                operations.add((route.path_format, method.lower()))
    return operations


_base_openapi = app.openapi


def openapi_with_public_read() -> dict[str, Any]:
    """FastAPI traegt bei jeder Route mit Schluessel-Dependency eine Schluesselpflicht ins Schema ein, auch dort,
    wo require("read") bei DOI_PUBLIC_READ=true ohne Schluessel durchlaesst. Generierte Clients verlangten dann
    selbst fuer GET /v1/status einen Schluessel. Deshalb bekommen diese Routen die leere Anforderung {} als
    Alternative. Die Pruefung selbst aendert sich dadurch nicht, poe-, write- und admin-Routen bleiben
    schluesselpflichtig."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = _base_openapi()
    if settings.public_read:
        paths = schema.get("paths", {})
        for path, method in public_read_operations():
            operation = paths.get(path, {}).get(method)
            if not operation:
                continue
            security = operation.setdefault("security", [])
            if {} not in security:
                security.append({})
    app.openapi_schema = schema
    return schema


app.openapi = openapi_with_public_read  # type: ignore[method-assign]
