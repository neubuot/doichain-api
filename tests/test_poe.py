"""Tests fuer Proof of Existence, OpenAPI-Sicherheit und Kontingent-Adresse.

Die RPC-Schicht wird durch eine kleine Fake-Node ersetzt, es braucht weder Node noch Netz.
Die Umgebungsvariablen muessen vor dem Import der App gesetzt sein, weil config.py sie beim Import liest."""

import dataclasses
import hashlib
import json
import os
import tempfile
from types import SimpleNamespace

WRITE_KEY = "test-write-key-0000000000"
POE_KEY = "test-poe-key-00000000000000"
POE_KEY_KEYED = "test-poe-key-nachweis-0000000"
KEYED_ID = hashlib.sha256(POE_KEY_KEYED.encode()).hexdigest()[:16]

os.environ.update(
    {
        "DOI_PUBLIC_READ": "true",
        "DOI_API_KEYS_READ": "",
        "DOI_API_KEYS_ADMIN": "",
        "DOI_API_KEYS_WRITE": WRITE_KEY,
        "DOI_API_KEYS_POE": POE_KEY + "," + POE_KEY_KEYED,
        "DOI_POE_KEY_LIMITS": KEYED_ID + "=2",
        "DOI_POE_KEYED_PER_DAY": "3",
        "DOI_STATE_DIR": tempfile.mkdtemp(prefix="doichain-api-test-"),
        "DOI_RPC_URL": "http://127.0.0.1:9/",
        "DOI_RPC_USER": "",
        "DOI_RPC_PASSWORD": "",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from doichain_api import main, quota  # noqa: E402
from doichain_api.rpc import RPCError  # noqa: E402

assert main.settings.write_keys == (WRITE_KEY,), "config.py wurde vor dem Setzen der Testumgebung importiert"

EXPIRY = main.NAME_EXPIRY_BLOCKS
HASH = "ab" * 32
NAME = "poe/" + HASH
NEW_TXID = "f" * 64


def txid(n: int) -> str:
    return f"{n:064x}"


def block_hash(n: int) -> str:
    return f"b{n:063x}"


def block_time(height: int) -> int:
    return 1_700_000_000 + height * 600


def poe_value(hash_hex: str, note: str) -> str:
    return json.dumps({"v": 1, "alg": "sha256", "hash": hash_hex, "ts": "2026-01-01T00:00:00Z", "note": note}, separators=(",", ":"))


class FakeNode:
    """Antwortet auf die RPC-Methoden, die die PoE-Routen brauchen, und merkt sich alle Aufrufe."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.names: dict[str, dict] = {}
        self.histories: dict[str, list[dict]] = {}
        self.pending: dict[str, list[dict]] = {}
        self.txs: dict[str, dict] = {}
        self.tip = 100_000

    def add_history(self, name: str, ops: list[tuple[int, int, str, str]]) -> None:
        """ops: (Nummer der txid, Hoehe, Inhaberadresse, Notiz), aelteste zuerst. Die letzte Operation ist die aktuelle."""
        hash_hex = name.split("/", 1)[1]
        history = []
        for n, height, address, note in ops:
            expires_in = height + EXPIRY - self.tip
            history.append(
                {
                    "name": name,
                    "value": poe_value(hash_hex, note),
                    "txid": txid(n),
                    "vout": 0,
                    "address": address,
                    "height": height,
                    "expires_in": expires_in,
                    "expired": expires_in <= 0,
                }
            )
            self.txs[txid(n)] = {
                "txid": txid(n),
                "blockhash": block_hash(n),
                "blocktime": block_time(height),
                "confirmations": self.tip - height + 1,
            }
        self.histories[name] = history
        self.names[name] = {**history[-1], "ismine": True}

    async def call(self, method: str, *params, wallet: bool = False, named: dict | None = None):
        self.calls.append((method, params))
        if method == "name_show":
            if params[0] not in self.names:
                raise RPCError(-4, "name not found")
            return dict(self.names[params[0]])
        if method == "name_pending":
            return list(self.pending.get(params[0], []))
        if method == "name_history":
            if params[0] not in self.histories:
                raise RPCError(-4, "name not found")
            return [dict(h) for h in self.histories[params[0]]]
        if method == "getrawtransaction":
            return dict(self.txs[params[0]])
        if method == "name_doi":
            return NEW_TXID
        if method == "getmempoolentry":
            return {"fees": {"base": 0.0003}, "vsize": 250}
        if method == "getbalances":
            return {"mine": {"trusted": 100.0, "untrusted_pending": 0.0, "immature": 0.0}}
        raise AssertionError(f"unerwarteter RPC-Aufruf {method}")

    def methods(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture
def node(monkeypatch):
    fake = FakeNode()
    monkeypatch.setattr(main.rpc, "call", fake.call)
    return fake


@pytest.fixture
def client():
    # Ohne with-Block, damit die Lifespan-Routine keinen echten RPC-Client startet.
    return TestClient(main.app)


# ---------------------------------------------------------------------------
# Nachweis anlegen
# ---------------------------------------------------------------------------

def test_expired_without_reanchor_gives_409_and_no_name_doi(node, client):
    node.add_history(NAME, [(1, 1000, "N1first", "erste")])
    response = client.post("/v1/poe", json={"hash": HASH, "note": "neu"}, headers={"X-API-Key": WRITE_KEY})
    assert response.status_code == 409
    message = response.json()["error"]["message"]
    assert "abgelaufen" in message
    assert "Block 1000" in message
    assert "reanchor=true" in message
    assert "name_doi" not in node.methods()


def test_expired_without_reanchor_does_not_use_public_quota(node, client):
    node.add_history(NAME, [(1, 1000, "N1first", "erste")])
    before = quota.usage("testclient")["used_ip"]
    response = client.post("/v1/poe", json={"hash": HASH}, headers={"X-API-Key": POE_KEY})
    assert response.status_code == 409
    assert quota.usage("testclient")["used_ip"] == before
    assert "name_doi" not in node.methods()


def test_expired_with_reanchor_calls_name_doi(node, client):
    node.add_history(NAME, [(1, 1000, "N1first", "erste")])
    response = client.post("/v1/poe", json={"hash": HASH, "note": "neu", "reanchor": True}, headers={"X-API-Key": WRITE_KEY})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reanchored_after_expiry"] is True
    assert body["renewed"] is True
    assert body["txid"] == NEW_TXID
    doi_calls = [params for method, params in node.calls if method == "name_doi"]
    assert len(doi_calls) == 1
    assert doi_calls[0][0] == NAME
    assert json.loads(doi_calls[0][1])["note"] == "neu"


def test_file_upload_expired_respects_reanchor_form_field(node, client):
    content = b"Vertrag Version 3"
    hash_hex = hashlib.sha256(content).hexdigest()
    node.add_history("poe/" + hash_hex, [(1, 1000, "N1first", "erste")])
    files = {"file": ("vertrag.txt", content, "text/plain")}
    refused = client.post("/v1/poe/file", files=files, headers={"X-API-Key": POE_KEY})
    assert refused.status_code == 409
    assert "name_doi" not in node.methods()
    accepted = client.post("/v1/poe/file", files=files, data={"reanchor": "true"}, headers={"X-API-Key": POE_KEY})
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    assert body["reanchored_after_expiry"] is True
    assert body["renewed"] is True
    assert body["file"] == {"name": "vertrag.txt", "size": len(content)}
    assert "quota" in body


@pytest.mark.parametrize("reanchor", [False, True])
def test_confirmed_gives_409_regardless_of_reanchor(node, client, reanchor):
    node.add_history(NAME, [(1, node.tip - 10, "N1first", "erste")])
    response = client.post("/v1/poe", json={"hash": HASH, "reanchor": reanchor}, headers={"X-API-Key": WRITE_KEY})
    assert response.status_code == 409
    assert "existiert bereits" in response.json()["error"]["message"]
    assert "name_doi" not in node.methods()


def test_confirmed_409_names_first_anchoring_after_reregistration(node, client):
    node.add_history(NAME, [(1, 1000, "N1first", "erste"), (2, 90_000, "N3other", "neu")])
    response = client.post("/v1/poe", json={"hash": HASH}, headers={"X-API-Key": WRITE_KEY})
    assert response.status_code == 409
    message = response.json()["error"]["message"]
    assert "erste Verankerung in Block 1000" in message
    assert "90000" not in message
    assert "name_doi" not in node.methods()


def test_pending_gives_409(node, client):
    node.pending[NAME] = [{"txid": txid(9), "op": "name_doi", "address": "N9", "value": "{}"}]
    response = client.post("/v1/poe", json={"hash": HASH, "reanchor": True}, headers={"X-API-Key": WRITE_KEY})
    assert response.status_code == 409
    assert "name_doi" not in node.methods()


def test_unknown_hash_registers_without_reanchor_flag(node, client):
    response = client.post("/v1/poe", json={"hash": HASH}, headers={"X-API-Key": WRITE_KEY})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reanchored_after_expiry"] is False
    assert body["renewed"] is False
    assert "name_doi" in node.methods()


# ---------------------------------------------------------------------------
# Nachweis pruefen
# ---------------------------------------------------------------------------

def test_status_single_registration(node, client):
    node.add_history(NAME, [(1, 90_000, "N1first", "erste")])
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["status"] == "confirmed"
    first = body["first_anchored"]
    assert first["txid"] == body["txid"] == txid(1)
    assert first["height"] == body["height"] == 90_000
    assert first["block_hash"] == body["block_hash"] == block_hash(1)
    assert first["value"] == body["value"]
    assert first["value_json"] == body["value_json"]
    assert first["value_json"]["note"] == "erste"
    assert first["owner_address"] == body["owner_address"] == "N1first"
    assert first["block_time_iso"] == body["block_time_iso"]
    assert first["registrations"] == 1
    assert body["reregistered_after_expiry"] is False
    assert body["current_registration_start"] is None
    # Nur eine Transaktion wird gelesen, die aktuelle.
    assert node.methods().count("getrawtransaction") == 1


def test_status_reregistered_after_expiry(node, client):
    second = node.tip - 100
    first_height = second - EXPIRY - 5
    node.add_history(NAME, [(1, first_height, "N1first", "erste"), (2, second, "N3other", "neu")])
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["status"] == "confirmed"
    # Oberste Ebene: aktuelle Registrierung
    assert body["txid"] == txid(2)
    assert body["owner_address"] == "N3other"
    assert body["value_json"]["note"] == "neu"
    # first_anchored: vollstaendig aus der ersten Operation, nichts gemischt
    first = body["first_anchored"]
    assert first["txid"] == txid(1)
    assert first["height"] == first_height
    assert first["block_hash"] == block_hash(1)
    assert first["block_time"] == block_time(first_height)
    assert first["owner_address"] == "N1first"
    assert first["value_json"]["note"] == "erste"
    assert json.loads(first["value"])["note"] == "erste"
    assert first["registrations"] == 2
    assert body["reregistered_after_expiry"] is True
    start = body["current_registration_start"]
    assert start["txid"] == txid(2)
    assert start["height"] == second
    assert start["block_time_iso"] == main.iso(block_time(second))
    assert start["explorer_tx"].endswith(txid(2))
    # Aktuelle und erste Transaktion, die aktuelle nicht doppelt.
    assert node.methods().count("getrawtransaction") == 2


def test_status_reregistered_then_updated_by_new_holder(node, client):
    node.add_history(NAME, [(1, 1000, "N1first", "erste"), (2, 40_000, "N3other", "neu"), (3, 41_000, "N3other", "neu2")])
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["txid"] == txid(3)
    assert body["first_anchored"]["txid"] == txid(1)
    assert body["first_anchored"]["owner_address"] == "N1first"
    assert body["reregistered_after_expiry"] is True
    assert body["current_registration_start"]["txid"] == txid(2)
    assert body["current_registration_start"]["height"] == 40_000


@pytest.mark.parametrize("gap, reregistered", [(EXPIRY - 1, False), (EXPIRY, True)])
def test_status_gap_boundary(node, client, gap, reregistered):
    node.add_history(NAME, [(1, 1000, "N1first", "erste"), (2, 1000 + gap, "N1first", "aktualisiert")])
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["reregistered_after_expiry"] is reregistered


def test_status_update_by_holder_before_expiry(node, client):
    node.add_history(NAME, [(1, 1000, "N1first", "erste"), (2, 1000 + EXPIRY - 1, "N1first", "verlaengert")])
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["reregistered_after_expiry"] is False
    assert body["current_registration_start"] is None
    first = body["first_anchored"]
    assert first["txid"] == txid(1)
    assert first["block_hash"] == block_hash(1)
    assert first["value_json"]["note"] == "erste"
    assert first["owner_address"] == "N1first"
    assert body["value_json"]["note"] == "verlaengert"


def test_status_without_name_history(node, client, monkeypatch):
    node.add_history(NAME, [(1, 90_000, "N1first", "erste")])
    original = node.call

    async def no_history(method, *params, **kwargs):
        if method == "name_history":
            raise RPCError(-1, "name_history is disabled, use -namehistory")
        return await original(method, *params, **kwargs)

    monkeypatch.setattr(main.rpc, "call", no_history)
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["first_anchored"]["registrations"] is None
    # Ohne Historie ist unbekannt, wer bei der ersten Verankerung Inhaber war.
    assert body["first_anchored"]["owner_address"] is None
    assert body["first_anchored"]["txid"] == body["txid"]
    assert body["owner_address"] == "N1first"
    assert body["reregistered_after_expiry"] is False
    assert body["current_registration_start"] is None


def test_status_unknown_has_stable_shape(node, client):
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["status"] == "unknown"
    assert body["reregistered_after_expiry"] is False
    assert body["current_registration_start"] is None
    assert "first_anchored" not in body


def test_verify_json_and_file_return_same_fields(node, client):
    content = b"Protokoll"
    hash_hex = hashlib.sha256(content).hexdigest()
    node.add_history("poe/" + hash_hex, [(1, 1000, "N1first", "erste"), (2, 1000 + EXPIRY, "N3other", "neu")])
    by_json = client.post("/v1/poe/verify", json={"hash": hash_hex}).json()
    by_file = client.post("/v1/poe/verify/file", files={"file": ("p.txt", content, "text/plain")}).json()
    for body in (by_json, by_file):
        assert body["reregistered_after_expiry"] is True
        assert body["first_anchored"]["owner_address"] == "N1first"


def test_value_json_is_object_or_null(node, client):
    for raw in ("123", '"x"', "[1]", "kein json"):
        assert main.parse_value_json(raw) is None, raw
    assert main.parse_value_json('{"note":"x"}') == {"note": "x"}
    node.add_history(NAME, [(1, 90_000, "N1first", "erste")])
    node.histories[NAME][0]["value"] = "[1]"
    node.names[NAME]["value"] = "[1]"
    body = client.get(f"/v1/poe/{HASH}").json()
    assert body["value"] == "[1]"
    assert body["value_json"] is None
    assert body["first_anchored"]["value"] == "[1]"
    assert body["first_anchored"]["value_json"] is None


def test_registration_start_index():
    def ops(*heights):
        return [{"txid": txid(i), "height": h} for i, h in enumerate(heights)]

    assert main.registration_start_index([]) is None
    assert main.registration_start_index(ops(10)) is None
    assert main.registration_start_index(ops(10, 10 + EXPIRY - 1)) is None
    assert main.registration_start_index(ops(10, 10 + EXPIRY)) == 1
    # Zwei Neuregistrierungen: die aktuelle Registrierung beginnt bei der letzten.
    assert main.registration_start_index(ops(10, 10 + EXPIRY, 10 + 2 * EXPIRY + 3, 10 + 2 * EXPIRY + 50)) == 2
    # Fehlende Hoehe wird uebersprungen statt geraten.
    assert main.registration_start_index([{"txid": txid(1)}, {"txid": txid(2), "height": 10 + EXPIRY}]) is None


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_openapi():
    main.app.openapi_schema = None
    yield
    main.app.openapi_schema = None


def test_openapi_marks_public_read_routes(client, fresh_openapi):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    def security(path, method):
        return paths[path][method].get("security", [])

    for path, method in (("/v1/status", "get"), ("/v1/poe/{hash}", "get"), ("/v1/names", "get"), ("/v1/name/{name}", "get"), ("/v1/poe/verify", "post")):
        assert {} in security(path, method), (path, method)
        assert {"ApiKey": []} in security(path, method), (path, method)
    for path, method in (("/v1/poe", "post"), ("/v1/poe/file", "post"), ("/v1/poe/quota", "get"), ("/v1/wallet", "get"), ("/v1/name/doi", "post"), ("/v1/rpc", "post")):
        assert security(path, method), (path, method)
        assert {} not in security(path, method), (path, method)
    assert "security" not in paths["/health"]["get"]
    poe_create = schema["components"]["schemas"]["PoeCreate"]["properties"]
    assert poe_create["reanchor"]["default"] is False


def test_openapi_without_public_read_keeps_key_requirement(client, fresh_openapi, monkeypatch):
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, public_read=False))
    schema = client.get("/openapi.json").json()
    assert {} not in schema["paths"]["/v1/status"]["get"]["security"]


def test_openapi_is_stable_across_calls(client, fresh_openapi):
    first = client.get("/openapi.json").json()
    second = client.get("/openapi.json").json()
    assert first == second
    assert first["paths"]["/v1/status"]["get"]["security"].count({}) == 1


# ---------------------------------------------------------------------------
# Kontingent-Adresse
# ---------------------------------------------------------------------------

def request_from(host):
    return SimpleNamespace(client=SimpleNamespace(host=host) if host is not None else None)


@pytest.mark.parametrize(
    "host, expected",
    [
        ("::ffff:1.2.3.4", "1.2.3.4"),
        ("::ffff:0102:0304", "1.2.3.4"),
        ("1.2.3.4", "1.2.3.4"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
        ("testclient", "testclient"),
        (None, "unbekannt"),
    ],
)
def test_client_ip(host, expected):
    assert main.client_ip(request_from(host)) == expected


# ---------------------------------------------------------------------------
# Kontingent je Schluessel (1.6.0)
# ---------------------------------------------------------------------------

def test_keyed_quota_counts_per_key_and_reports_key_id(node, client):
    before = quota.usage("testclient")["used_ip"]
    q = client.get("/v1/poe/quota", headers={"X-API-Key": POE_KEY_KEYED}).json()
    assert q["key_id"] == KEYED_ID and q["scope"] == "key" and q["per_ip_day"] == 2 and q["per_day"] == 3
    r1 = client.post("/v1/poe", json={"hash": "c1" * 32, "note": "eins"}, headers={"X-API-Key": POE_KEY_KEYED})
    r2 = client.post("/v1/poe", json={"hash": "c2" * 32, "note": "zwei"}, headers={"X-API-Key": POE_KEY_KEYED})
    assert r1.status_code == 201 and r2.status_code == 201
    assert r2.json()["quota"]["remaining_ip"] == 0 and r2.json()["quota"]["scope"] == "key"
    r3 = client.post("/v1/poe", json={"hash": "c3" * 32, "note": "drei"}, headers={"X-API-Key": POE_KEY_KEYED})
    assert r3.status_code == 429
    assert "Schluessels" in r3.json()["error"]["message"]
    # Das IP-Kontingent der oeffentlichen App bleibt unberuehrt.
    assert quota.usage("testclient")["used_ip"] == before
    assert quota.usage("testclient")["used_total"] == before
    # Der oeffentliche poe-Schluessel zaehlt weiter je IP und nennt seinen Fingerprint.
    q2 = client.get("/v1/poe/quota", headers={"X-API-Key": POE_KEY}).json()
    assert q2["scope"] == "ip" and q2["key_id"] == hashlib.sha256(POE_KEY.encode()).hexdigest()[:16]


def test_keyed_quota_released_when_anchoring_fails(node, client, monkeypatch):
    async def failing_call(method, *params, wallet=False, named=None):
        if method == "name_doi":
            raise RPCError(-6, "Insufficient funds")
        return await node.call(method, *params, wallet=wallet, named=named)
    monkeypatch.setattr(main.rpc, "call", failing_call)
    ident = quota.KEY_PREFIX + KEYED_ID
    before = quota.usage(ident, per_ip_day=2, per_day=3)["used_ip"]
    response = client.post("/v1/poe", json={"hash": "c4" * 32}, headers={"X-API-Key": POE_KEY_KEYED})
    assert response.status_code != 201
    assert quota.usage(ident, per_ip_day=2, per_day=3)["used_ip"] == before


def test_key_fingerprint_is_stable():
    from doichain_api.auth import key_fingerprint
    assert key_fingerprint(POE_KEY_KEYED) == KEYED_ID
    assert len(key_fingerprint("x" * 20)) == 16


# ---------------------------------------------------------------------------
# Einschlussnachweis GET /v1/tx/{txid}/proof (1.6.0)
# ---------------------------------------------------------------------------

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def reference_root(txids: list[str]) -> str:
    level = [bytes.fromhex(t)[::-1] for t in txids]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256d(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0][::-1].hex()


def apply_branch(txid_hex: str, branch: list[str], index: int) -> str:
    h = bytes.fromhex(txid_hex)[::-1]
    for sibling in branch:
        s = bytes.fromhex(sibling)[::-1]
        h = sha256d(s + h) if index & 1 else sha256d(h + s)
        index //= 2
    return h[::-1].hex()


@pytest.mark.parametrize("n_tx,index", [(1, 0), (2, 1), (3, 2), (5, 3)])
def test_merkle_branch_reaches_root(n_tx, index):
    txids = [hashlib.sha256(f"tx{i}".encode()).hexdigest() for i in range(n_tx)]
    branch, root = main.merkle_branch(txids, index)
    assert root == reference_root(txids)
    assert apply_branch(txids[index], branch, index) == root
    assert len(branch) == (0 if n_tx == 1 else (n_tx - 1).bit_length())


def fake_block(txids: list[str]) -> tuple[str, str]:
    """Header mit passender Merkle-Wurzel, Blockhash ist das doppelte SHA-256 des Headers."""
    root = bytes.fromhex(reference_root(txids))[::-1]
    header = (1).to_bytes(4, "little") + b"\x11" * 32 + root + (1_790_000_000).to_bytes(4, "little") + b"\xff\xff\x00\x1d" + (7).to_bytes(4, "little")
    assert len(header) == 80
    return header.hex(), sha256d(header)[::-1].hex()


def test_tx_proof_delivers_header_branch_and_txoutproof(node, client, monkeypatch):
    txids = [hashlib.sha256(f"block-tx{i}".encode()).hexdigest() for i in range(3)]
    header_hex, block_hash = fake_block(txids)
    target = txids[2]

    async def fake_call(method, *params, wallet=False, named=None):
        if method == "getrawtransaction":
            return {"txid": params[0], "hex": "00aa", "blockhash": block_hash, "confirmations": 9}
        if method == "getblock" and params[1] == 1:
            return {"hash": block_hash, "height": 435900, "time": 1_790_000_000, "merkleroot": reference_root(txids), "tx": txids}
        if method == "getblock" and params[1] == 0:
            return header_hex + "deadbeef"
        if method == "gettxoutproof":
            assert params[0] == [target] and params[1] == block_hash
            return "0100proof"
        raise AssertionError(method)
    monkeypatch.setattr(main.rpc, "call", fake_call)
    response = client.get(f"/v1/tx/{target}/proof")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["block"]["header_hex"] == header_hex and body["block"]["header_matches_hash"] is True
    assert body["merkle_root_matches"] is True and body["tx_index"] == 2
    assert apply_branch(target, body["merkle_branch"], body["tx_index"]) == body["block"]["merkleroot"]
    assert body["txoutproof_hex"] == "0100proof" and body["tx_hex"] == "00aa"
    assert body["chain_ref"]["height"] == 431018
    assert body["block"]["time_iso"].endswith("Z")


def test_tx_proof_unconfirmed_gives_409(node, client, monkeypatch):
    async def fake_call(method, *params, wallet=False, named=None):
        if method == "getrawtransaction":
            return {"txid": params[0], "hex": "00aa"}
        raise AssertionError(method)
    monkeypatch.setattr(main.rpc, "call", fake_call)
    response = client.get("/v1/tx/" + "d" * 64 + "/proof")
    assert response.status_code == 409
