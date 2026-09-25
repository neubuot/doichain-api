"""Minimaler ElectrumX-Client (JSON-RPC ueber TCP, eine Zeile je Nachricht) fuer
Adressguthaben und -historie. Doichain Core selbst hat keinen Adressindex,
der lokale ElectrumX auf doi-btc-node liefert diese Daten."""

import asyncio
import hashlib
import json
from typing import Any

from .config import settings

# Adressversionen des Doichain-Mainnets (chainparams.cpp): P2PKH 52 = "N…", P2SH 13 = "6…", Bech32-HRP "dc".
P2PKH_VERSION = 52
P2SH_VERSION = 13
BECH32_HRP = "dc"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


class AddressError(ValueError):
    pass


class ElectrumError(Exception):
    pass


def _sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _base58check_decode(address: str) -> tuple[int, bytes]:
    if not 26 <= len(address) <= 35:
        raise AddressError("Base58-Adresse hat die falsche Laenge")
    number = 0
    for char in address:
        index = _B58.find(char)
        if index < 0:
            raise AddressError("ungueltiges Zeichen in Base58-Adresse")
        number = number * 58 + index
    try:
        raw = number.to_bytes(25, "big")
    except OverflowError:
        raise AddressError("Base58-Adresse ist zu lang fuer eine Doichain-Adresse")
    padding = len(address) - len(address.lstrip("1"))
    raw = b"\x00" * padding + raw[padding:] if padding else raw
    if len(raw) != 25:
        raise AddressError("Base58-Adresse hat die falsche Laenge")
    payload, checksum = raw[:-4], raw[-4:]
    if _sha256d(payload)[:4] != checksum:
        raise AddressError("Pruefsumme der Adresse stimmt nicht")
    return payload[0], payload[1:]


def _bech32_polymod(values: list[int]) -> int:
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _bech32_decode(address: str) -> tuple[int, bytes]:
    """Bech32 (BIP173, Witness v0) dekodieren und (witness_version, program) liefern."""
    if address != address.lower() and address != address.upper():
        raise AddressError("Bech32-Adresse mischt Gross- und Kleinschreibung")
    address = address.lower()
    pos = address.rfind("1")
    if pos < 1 or pos + 7 > len(address) or len(address) > 90:
        raise AddressError("Bech32-Adresse fehlerhaft")
    hrp, data_part = address[:pos], address[pos + 1:]
    if hrp != BECH32_HRP:
        raise AddressError(f"Bech32-Praefix '{hrp}' gehoert nicht zum Doichain-Mainnet ('{BECH32_HRP}')")
    if any(c not in _BECH32_CHARSET for c in data_part):
        raise AddressError("ungueltiges Zeichen in Bech32-Adresse")
    data = [_BECH32_CHARSET.find(c) for c in data_part]
    if _bech32_polymod(_bech32_hrp_expand(hrp) + data) != 1:
        raise AddressError("Bech32-Pruefsumme stimmt nicht (nur Witness v0 wird unterstuetzt)")
    witness_version, payload = data[0], data[1:-6]
    if witness_version != 0:
        raise AddressError("nur SegWit v0 (dc1q…) wird unterstuetzt")
    acc = bits = 0
    program = bytearray()
    for value in payload:
        acc = (acc << 5) | value
        bits += 5
        while bits >= 8:
            bits -= 8
            program.append((acc >> bits) & 0xFF)
    if bits >= 5 or ((acc << (8 - bits)) & 0xFF):
        raise AddressError("Bech32-Padding fehlerhaft")
    if len(program) not in (20, 32):
        raise AddressError("Witness-Programm hat die falsche Laenge")
    return witness_version, bytes(program)


def script_pubkey_for_address(address: str) -> bytes:
    """scriptPubKey einer Doichain-Adresse (N…, 6…, dc1q…) berechnen."""
    address = address.strip()
    if address.lower().startswith(BECH32_HRP + "1"):
        _, program = _bech32_decode(address)
        return bytes([0x00, len(program)]) + program
    version, hash160 = _base58check_decode(address)
    if len(hash160) != 20:
        raise AddressError("Hash der Adresse hat die falsche Laenge")
    if version == P2PKH_VERSION:
        return b"\x76\xa9\x14" + hash160 + b"\x88\xac"
    if version == P2SH_VERSION:
        return b"\xa9\x14" + hash160 + b"\x87"
    raise AddressError(f"Adressversion {version} gehoert nicht zum Doichain-Mainnet (erwartet {P2PKH_VERSION} oder {P2SH_VERSION})")


def scripthash_for_address(address: str) -> str:
    """Electrum-Scripthash: sha256(scriptPubKey), Bytes umgekehrt, hex."""
    return hashlib.sha256(script_pubkey_for_address(address)).digest()[::-1].hex()


async def electrum_call(method: str, *params: Any, timeout: float = 15.0) -> Any:
    """Eine Anfrage an den lokalen ElectrumX schicken (neue Verbindung je Aufruf)."""
    try:
        # Historien grosser Adressen (Pools) sind mehrere Megabyte lang, deshalb ein grosszuegiges Zeilenlimit.
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.electrum_host, settings.electrum_port, limit=64 * 1024 * 1024),
            timeout=5.0,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise ElectrumError(f"ElectrumX nicht erreichbar: {exc.__class__.__name__}") from exc
    try:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "server.version", "params": ["doichain-api", "1.4"]},
            {"jsonrpc": "2.0", "id": 2, "method": method, "params": list(params)},
        ]
        writer.write(("\n".join(json.dumps(m) for m in messages) + "\n").encode())
        await writer.drain()
        result: Any = None
        got_result = False
        for _ in range(2):
            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            if not line:
                raise ElectrumError("ElectrumX hat die Verbindung beendet")
            try:
                reply = json.loads(line)
            except ValueError as exc:
                raise ElectrumError("ElectrumX hat kein gueltiges JSON geliefert") from exc
            if not isinstance(reply, dict):
                raise ElectrumError("ElectrumX hat eine unerwartete Antwort geliefert")
            error = reply.get("error")
            if error:
                message = error.get("message", error) if isinstance(error, dict) else error
                raise ElectrumError(f"ElectrumX meldet: {message}")
            if reply.get("id") == 2:
                result = reply.get("result")
                got_result = True
        if not got_result:
            raise ElectrumError("ElectrumX hat die Anfrage nicht beantwortet")
        return result
    except (asyncio.TimeoutError, ValueError, asyncio.LimitOverrunError) as exc:
        raise ElectrumError(f"ElectrumX-Antwort unbrauchbar oder zu spaet ({exc.__class__.__name__})") from exc
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
