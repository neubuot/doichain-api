"""Tests fuer das Verbrauchsbuch (ledger.py) und die Betriebsauskunft GET /v1/wallet/report.

Die Umgebung entspricht der aus test_poe.py, damit die Reihenfolge der Testmodule keine Rolle spielt
(config.py liest die Umgebung nur beim ersten Import)."""

import dataclasses
import hashlib
import json
import os
import tempfile

WRITE_KEY = "test-write-key-0000000000"
POE_KEY = "test-poe-key-00000000000000"
POE_KEY_KEYED = "test-poe-key-nachweis-0000000"
KEYED_ID = hashlib.sha256(POE_KEY_KEYED.encode()).hexdigest()[:16]
WRITE_ID = hashlib.sha256(WRITE_KEY.encode()).hexdigest()[:16]
POE_ID = hashlib.sha256(POE_KEY.encode()).hexdigest()[:16]
ADMIN_KEY = "test-admin-key-000000000000"

for _name, _value in {
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
}.items():
    os.environ.setdefault(_name, _value)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from doichain_api import auth, ledger, main  # noqa: E402

NOW = 1_800_000_000
DAY = 86400


def txid(n: int) -> str:
    return f"{n:064x}"


def value(note: str | None = None, **extra) -> str:
    v = {"v": 1, "alg": "sha256", "hash": "ab" * 32, "ts": "2026-01-01T00:00:00Z", **extra}
    if note:
        v["note"] = note
    return json.dumps(v)


def send(n: int, age_days: float, fee: float = 0.0105, amount: float = 0.0, **extra) -> dict:
    return {"txid": txid(n), "category": "send", "amount": -amount, "fee": -fee, "time": int(NOW - age_days * DAY), "confirmations": 3, "name": f"update: 'poe/{n}'", **extra}


@pytest.fixture
def book(monkeypatch, tmp_path):
    """Frisches Verbrauchsbuch und Verbraucherdatei je Test."""
    consumers = tmp_path / "consumers.json"
    consumers.write_text(json.dumps({
        "keys": {WRITE_ID: {"name": "BlockPro"}, POE_ID: {"name": "Oeffentlicher Schluessel", "shared": True}},
        "patterns": [{"match": "^blockpro:", "name": "BlockPro"}, {"match": "^Screenshot ", "name": "Screenshot PoE"}],
    }), encoding="utf-8")
    settings = dataclasses.replace(ledger.settings, state_dir=str(tmp_path), consumers_file=str(consumers), admin_keys=(ADMIN_KEY,), report_allow=("203.0.113.7", "2001:db8::/64"))
    for module in (ledger, main, auth):
        monkeypatch.setattr(module, "settings", settings)
    monkeypatch.setattr(ledger, "_consumers_cache", None)
    monkeypatch.setitem(main._report_cache, "data", None)
    return settings


def test_sync_costs_and_removal(book):
    stats = ledger.sync([send(1, 1), send(2, 2, fee=0.0002, amount=3.0), {"txid": txid(3), "category": "send", "amount": 0, "fee": -0.01, "abandoned": True, "time": NOW}], last_block="b1")
    assert stats["added"] == 2 and stats["removed"] == 1
    report = ledger.report(balance=100.0, pending=0.0, reserve=5.0, now=NOW)
    assert report["ledger"]["transactions"] == 2
    assert report["ledger"]["spent_total"] == pytest.approx(0.0105 + 3.0002)
    assert ledger.meta("last_block") == "b1"
    # Wird eine Transaktion spaeter verdraengt, verschwindet sie aus dem Buch.
    ledger.sync([{**send(1, 1), "confirmations": -1}])
    assert ledger.report(balance=100.0, pending=0.0, reserve=5.0, now=NOW)["ledger"]["transactions"] == 1


def test_sync_is_idempotent_and_keeps_api_attribution(book):
    ledger.record(txid(1), route="poe", key_id=WRITE_ID, name="poe/1", note="blockpro:v1:x")
    assert ledger.report(balance=1.0, pending=0.0, reserve=5.0, now=NOW)["ledger"]["waiting_for_wallet"] == 1
    for _ in range(2):
        ledger.sync([send(1, 0.5)])
    report = ledger.report(balance=1.0, pending=0.0, reserve=5.0, now=NOW)
    assert report["ledger"]["transactions"] == 1 and report["ledger"]["waiting_for_wallet"] == 0
    assert report["consumers"][0]["name"] == "BlockPro"
    assert report["consumers"][0]["kind"] == "key"
    assert report["consumers"][0]["key_ids"] == [WRITE_ID]


def test_consumer_resolution(book):
    ledger.record(txid(1), route="poe", key_id=WRITE_ID, note="irgendwas")  # eigener Schluessel schlaegt Notiz
    ledger.record(txid(2), route="poe", key_id=POE_ID, note="Screenshot example.org")  # geteilter Schluessel: Muster zuerst
    ledger.record(txid(3), route="poe", key_id=POE_ID, note="ohne Muster")  # geteilter Schluessel: Rueckfall auf den Namen
    ledger.record(txid(4), route="poe", key_id="0123456789abcdef")  # unbekannter Schluessel
    ledger.record(txid(5), route="public")
    ledger.record(txid(6), route="seal", ident="gh:neubuot/kerbholz", note="SHA256SUMS")
    history = {txid(7): value("blockpro:v1:20261101T2200Z"), txid(8): value(), txid(9): value(None, gh={"repo": "a/b", "ref": "v1", "sha": "x"}, file="SHA256SUMS")}
    ledger.sync([send(n, 1) for n in range(1, 10)], history)
    names = {c["name"]: c for c in ledger.report(balance=50.0, pending=0.0, reserve=5.0, now=NOW)["consumers"]}
    assert names["BlockPro"]["tx_total"] == 2  # Schluessel und Notizmuster der Historie
    assert names["Screenshot PoE"]["tx_total"] == 1
    assert names["Oeffentlicher Schluessel"]["tx_total"] == 1
    assert names["Schlüssel 0123456789abcdef (ohne Namen)"]["tx_total"] == 1
    assert names["Öffentlich ohne Schlüssel"]["tx_total"] == 1
    assert names["Doichain Seal (GitHub-Releases)"]["tx_total"] == 2
    assert names["Nicht zugeordnet (vor dem Verbrauchsbuch oder direkt am Wallet)"]["tx_total"] == 1


def test_report_windows_runway_and_days(book):
    # Zehn Tage lang 1 DOI je Tag, heute 0,5 DOI.
    txs = [send(n, n + 0.5, fee=1.0) for n in range(1, 11)] + [send(99, 0.1, fee=0.5)]
    ledger.sync(txs + [{"txid": txid(500), "category": "receive", "amount": 400.0, "vout": 1, "address": "Nfund", "label": "api-funding", "time": NOW - 3 * DAY, "confirmations": 30}])
    report = ledger.report(balance=75.0, pending=0.0, reserve=5.0, now=NOW)
    assert report["burn"]["tx_24h"] == 1 and report["burn"]["last_24h"] == pytest.approx(0.5)
    assert report["burn"]["per_day_7d"] == pytest.approx(6.5 / 7)
    assert report["runway"]["public_pause_days"] == pytest.approx(70 / (6.5 / 7), abs=0.06)
    assert report["runway"]["empty_days"] > report["runway"]["public_pause_days"]
    assert report["wallet"] == {"balance": 75.0, "pending": 0.0, "reserve": 5.0, "usable": 70.0, "public_poe_available": True}
    assert len(report["days"]) == 30 and report["days"][-1]["cost"] == pytest.approx(0.5)
    assert sum(d["tx"] for d in report["days"]) == 11
    assert report["deposits"][0]["amount"] == 400.0 and report["deposits_total"] == {"amount": 400.0, "count": 1}
    assert report["recent"][0]["txid"] == txid(99)
    # Wechselgeld eigener Ausgaben ist keine Einzahlung.
    ledger.sync([{"txid": txid(1), "category": "receive", "amount": 4.0, "vout": 1, "time": NOW, "confirmations": 1}, send(1, 1.5, fee=1.0)])
    assert ledger.report(balance=75.0, pending=0.0, reserve=5.0, now=NOW)["deposits_total"]["count"] == 1


def test_report_without_spends_and_below_reserve(book):
    report = ledger.report(balance=4.0, pending=0.0, reserve=5.0, now=NOW)
    assert report["wallet"]["public_poe_available"] is False and report["wallet"]["usable"] == 0.0
    assert report["runway"]["public_pause_days"] is None and report["consumers"] == []


def test_broken_consumers_file_is_ignored(book):
    with open(book.consumers_file, "w", encoding="utf-8") as fh:
        fh.write("{kaputt")
    ledger.sync([send(1, 1)], {txid(1): value("blockpro:v1:x")})
    assert ledger.report(balance=1.0, pending=0.0, reserve=5.0, now=NOW)["consumers"][0]["kind"] == "wallet"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

class WalletNode:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def call(self, method: str, *params, wallet: bool = False, named: dict | None = None):
        self.calls.append((method, params))
        if method == "listsinceblock":
            return {"transactions": [send(1, 0.01)], "lastblock": "b" * 64}
        if method == "name_list":
            return [{"name": "poe/1", "txid": txid(1), "value": value("blockpro:v1:x")}]
        if method == "getbalances":
            return {"mine": {"trusted": 504.0, "untrusted_pending": 0.0, "immature": 0.0}}
        if method == "getaddressesbylabel":
            return {"Nfunding": {"purpose": "receive"}}
        raise AssertionError(f"unerwarteter RPC-Aufruf {method}")


@pytest.fixture
def node(monkeypatch):
    fake = WalletNode()
    monkeypatch.setattr(main.rpc, "call", fake.call)
    return fake


def test_route_needs_admin_or_allowed_address(book, node):
    assert TestClient(main.app).get("/v1/wallet/report").status_code == 403
    assert TestClient(main.app).get("/v1/wallet/report", headers={"X-API-Key": WRITE_KEY}).status_code == 403
    assert TestClient(main.app, client=("198.51.100.1", 1)).get("/v1/wallet/report").status_code == 403
    assert node.calls == []
    ok = TestClient(main.app).get("/v1/wallet/report", headers={"X-API-Key": ADMIN_KEY})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["wallet"]["balance"] == 504.0 and body["funding"]["address"] == "Nfunding"
    assert body["consumers"][0]["name"] == "BlockPro"
    # Erster Lauf liest die Namen fuer die Zuordnung der Historie, die Antwort wird danach zwischengespeichert.
    methods = [c[0] for c in node.calls]
    assert methods.count("name_list") == 1
    assert TestClient(main.app, client=("203.0.113.7", 1)).get("/v1/wallet/report").status_code == 200
    assert TestClient(main.app, client=("2001:db8::42", 1)).get("/v1/wallet/report").status_code == 200
    assert [c[0] for c in node.calls] == methods


def test_second_sync_starts_at_last_block(book, node, monkeypatch):
    client = TestClient(main.app)
    assert client.get("/v1/wallet/report", headers={"X-API-Key": ADMIN_KEY}).status_code == 200
    monkeypatch.setitem(main._report_cache, "data", None)
    node.calls.clear()
    assert client.get("/v1/wallet/report", headers={"X-API-Key": ADMIN_KEY}).status_code == 200
    assert ("listsinceblock", ("b" * 64, 6)) in node.calls
    assert "name_list" not in [c[0] for c in node.calls]


def test_poe_create_books_key_and_note(book, monkeypatch):
    from tests.test_poe import FakeNode, NEW_TXID

    fake = FakeNode()
    monkeypatch.setattr(main.rpc, "call", fake.call)
    response = TestClient(main.app).post("/v1/poe", json={"hash": "cd" * 32, "note": "frei gewaehlt"}, headers={"X-API-Key": WRITE_KEY})
    assert response.status_code == 201, response.text
    ledger.sync([{"txid": NEW_TXID, "category": "send", "amount": 0, "fee": -0.0104, "time": NOW, "confirmations": 0}])
    report = ledger.report(balance=1.0, pending=0.0, reserve=5.0, now=NOW)
    assert report["consumers"][0]["name"] == "BlockPro" and report["recent"][0]["note"] == "frei gewaehlt"
    assert report["recent"][0]["route"] == "poe"
