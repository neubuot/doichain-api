"""Verbrauchsbuch des Node-Wallets: Wer hat welche Transaktion ausgeloest und was hat sie gekostet.

Jede schreibende Route traegt ihre Transaktion mit dem Fingerprint des Schluessels (nie mit dem Schluessel
selbst), der Route und der Notiz ein. Kosten und Zeit kommen danach aus dem Wallet (sync), ebenso alle
Transaktionen, die nicht ueber die API liefen, und die Einzahlungen. Aeltere Transaktionen aus der Zeit vor
dem Verbrauchsbuch werden ueber die Notiz im Wert des Namens zugeordnet (Muster in der Verbraucherdatei).

Die Verbraucherdatei (DOI_CONSUMERS_FILE, Standard /etc/doichain-api/consumers.json) ordnet Fingerprints und
Notizmuster einem Namen zu. Sie enthaelt keine Schluessel:

    {"keys": {"<fingerprint>": {"name": "BlockPro", "shared": false}},
     "patterns": [{"match": "^blockpro:", "name": "BlockPro"}]}

shared kennzeichnet einen Schluessel, den mehrere Anwendungen teilen (der oeffentliche poe-Schluessel). Dort
entscheidet zuerst das Notizmuster, der Name des Schluessels ist nur die Rueckfallebene."""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings

logger = logging.getLogger("doichain_api.ledger")
_lock = threading.Lock()
DAY = 86400
REPORT_DAYS = 30


def _connect() -> sqlite3.Connection:
    os.makedirs(settings.state_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(settings.state_dir, "ledger.db"), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "create table if not exists spend (txid text primary key, ts integer not null, cost real, route text, "
        "key_id text, ident text, name text, note text, source text not null)"
    )
    conn.execute("create index if not exists spend_ts on spend (ts)")
    conn.execute(
        "create table if not exists deposit (txid text not null, vout integer not null, ts integer not null, "
        "amount real not null, address text, label text, primary key (txid, vout))"
    )
    conn.execute("create table if not exists meta (k text primary key, v text)")
    return conn


def record(txid: str, *, route: str, key_id: str | None = None, ident: str | None = None, name: str | None = None, note: str | None = None) -> None:
    """Eine eben gesendete Transaktion eintragen. Scheitert nie nach aussen: Das Verbrauchsbuch darf keinen
    Schreibaufruf zu Fall bringen, die Transaktion ist dann laengst im Netz."""
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "insert into spend (txid, ts, cost, route, key_id, ident, name, note, source) values (?, ?, null, ?, ?, ?, ?, ?, 'api') "
                "on conflict(txid) do update set route = excluded.route, key_id = excluded.key_id, ident = excluded.ident, "
                "name = coalesce(excluded.name, spend.name), note = coalesce(excluded.note, spend.note), source = 'api'",
                (txid, int(time.time()), route, key_id, ident, name, (note or None) and note[:200]),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Verbrauchsbuch: Eintrag fuer %s fehlgeschlagen", txid)


def meta(key: str) -> str | None:
    with _lock, _connect() as conn:
        row = conn.execute("select v from meta where k = ?", (key,)).fetchone()
    return row["v"] if row else None


def note_of_value(value: Any) -> tuple[str | None, str | None]:
    """Notiz und Herkunft (gh:<owner/repo>) aus dem Wert eines PoE-Namens."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None, None
    if not isinstance(value, dict):
        return None, None
    gh = value.get("gh")
    repo = None
    if isinstance(gh, dict):
        repo = gh.get("repo") or gh.get("repository")
    elif isinstance(gh, str):
        repo = gh.split("@")[0]
    note = value.get("note") or value.get("file")
    return (str(note)[:200] if note else None), (f"gh:{repo}" if repo else ("gh:" if gh else None))


def sync(transactions: list[dict], values_by_txid: dict[str, Any] | None = None, *, last_block: str | None = None) -> dict:
    """Wallet-Transaktionen (listsinceblock) ins Verbrauchsbuch uebernehmen.

    Ausgaben: Kosten = gebundene 0,01 DOI des Namens plus Gebuehr (das Wallet meldet beides zusammen als fee),
    bei Auszahlungen zusaetzlich der Betrag. Verworfene und verdraengte Transaktionen kosten nichts und werden
    entfernt. Eingaenge landen in der Tabelle deposit."""
    values_by_txid = values_by_txid or {}
    spends: dict[str, dict] = {}
    gone: set[str] = set()
    deposits: list[tuple] = []
    for tx in transactions:
        txid = tx.get("txid")
        if not txid:
            continue
        category = tx.get("category")
        if tx.get("abandoned") or int(tx.get("confirmations") or 0) < 0:
            gone.add(txid)
            continue
        ts = int(tx.get("time") or tx.get("timereceived") or time.time())
        if category == "send":
            entry = spends.setdefault(txid, {"ts": ts, "amount": 0.0, "fee": 0.0, "name": None})
            entry["amount"] += abs(float(tx.get("amount") or 0))
            entry["fee"] = max(entry["fee"], abs(float(tx.get("fee") or 0)))
            if tx.get("name"):
                entry["name"] = str(tx["name"])[:120]
        elif category == "receive":
            deposits.append((txid, int(tx.get("vout") or 0), ts, float(tx.get("amount") or 0), tx.get("address"), tx.get("label")))
    added = 0
    with _lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for txid in gone:
                conn.execute("delete from spend where txid = ?", (txid,))
                conn.execute("delete from deposit where txid = ?", (txid,))
            for txid, e in spends.items():
                if txid in gone:
                    continue
                cost = round(e["amount"] + e["fee"], 8)
                known = conn.execute("select 1 from spend where txid = ?", (txid,)).fetchone()
                if known:
                    conn.execute("update spend set cost = ?, ts = ?, name = coalesce(name, ?) where txid = ?", (cost, e["ts"], e["name"], txid))
                    continue
                note, ident = note_of_value(values_by_txid.get(txid))
                conn.execute(
                    "insert into spend (txid, ts, cost, route, key_id, ident, name, note, source) values (?, ?, ?, null, null, ?, ?, ?, 'wallet')",
                    (txid, e["ts"], cost, ident, e["name"], note),
                )
                added += 1
            for row in deposits:
                if row[0] in gone or row[0] in spends:
                    # Wechselgeld und Namensausgaenge eigener Transaktionen sind keine Einzahlung.
                    continue
                conn.execute("insert or replace into deposit (txid, vout, ts, amount, address, label) values (?, ?, ?, ?, ?, ?)", row)
            if last_block:
                conn.execute("insert into meta (k, v) values ('last_block', ?) on conflict(k) do update set v = excluded.v", (last_block,))
            conn.execute("insert into meta (k, v) values ('last_sync', ?) on conflict(k) do update set v = excluded.v", (str(int(time.time())),))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"spends": len(spends), "added": added, "deposits": len(deposits), "removed": len(gone)}


# ---------------------------------------------------------------------------
# Verbraucher zuordnen
# ---------------------------------------------------------------------------

_consumers_cache: tuple[float, dict] | None = None


def load_consumers(path: str | None = None) -> dict:
    """Verbraucherdatei lesen (mit Zwischenspeicher je Aenderungszeit). Fehlt sie oder ist sie fehlerhaft,
    gilt eine leere Zuordnung, die Auskunft bleibt trotzdem benutzbar."""
    global _consumers_cache
    path = path or settings.consumers_file
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"keys": {}, "patterns": []}
    if _consumers_cache and _consumers_cache[0] == mtime:
        return _consumers_cache[1]
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        keys = {str(k).lower(): {"name": str(v.get("name") or k), "shared": bool(v.get("shared"))} for k, v in (raw.get("keys") or {}).items() if isinstance(v, dict)}
        patterns = [{"re": re.compile(p["match"]), "name": str(p["name"])} for p in (raw.get("patterns") or []) if p.get("match") and p.get("name")]
        data = {"keys": keys, "patterns": patterns}
    except (OSError, ValueError, KeyError, re.error, AttributeError):
        logger.exception("Verbraucherdatei %s ist fehlerhaft und wird ignoriert", path)
        data = {"keys": {}, "patterns": []}
    _consumers_cache = (mtime, data)
    return data


def consumer_of(row: Any, consumers: dict) -> tuple[str, str]:
    """Name und Art des Verbrauchers einer Zeile. Art: key (eigener Schluessel), seal (GitHub-Siegel),
    pattern (ueber die Notiz erkannt), public (ohne Schluessel), wallet (nicht ueber die API), unknown."""
    key_id = row["key_id"]
    ident = row["ident"] or ""
    note = row["note"] or ""
    key = consumers["keys"].get(key_id) if key_id else None
    if ident.startswith("gh:"):
        return "Doichain Seal (GitHub-Releases)", "seal"
    if key and not key["shared"]:
        return key["name"], "key"
    for pattern in consumers["patterns"]:
        if note and pattern["re"].search(note):
            return pattern["name"], "pattern"
    if key:
        return key["name"], "key"
    if key_id:
        return f"Schlüssel {key_id} (ohne Namen)", "key"
    if row["route"] == "public":
        return "Öffentlich ohne Schlüssel", "public"
    if row["route"] == "send":
        return "Auszahlung (admin)", "key"
    if row["source"] == "wallet":
        return "Nicht zugeordnet (vor dem Verbrauchsbuch oder direkt am Wallet)", "wallet"
    return "Nicht zugeordnet", "unknown"


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def report(*, balance: float, pending: float, reserve: float, now: int | None = None, consumers: dict | None = None) -> dict:
    """Auswertung des Verbrauchsbuchs: Verbrauch je Verbraucher und Tag, Reichweite, Einzahlungen."""
    now = now or int(time.time())
    consumers = consumers or load_consumers()
    with _lock, _connect() as conn:
        rows = conn.execute("select * from spend where cost is not null order by ts").fetchall()
        open_rows = conn.execute("select count(*) as n from spend where cost is null").fetchone()["n"]
        deposits = conn.execute("select * from deposit order by ts desc limit 10").fetchall()
        deposit_total = conn.execute("select coalesce(sum(amount), 0) as s, count(*) as n from deposit").fetchone()
        first_api = conn.execute("select min(ts) as t from spend where source = 'api'").fetchone()["t"]
    today = datetime.fromtimestamp(now, tz=timezone.utc).date()
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(REPORT_DAYS - 1, -1, -1)]
    days = {d: {"day": d, "tx": 0, "cost": 0.0, "by": {}} for d in day_keys}
    per: dict[str, dict] = {}
    windows = (("24h", DAY), ("7d", 7 * DAY), ("30d", 30 * DAY))
    totals = {w: {"tx": 0, "cost": 0.0} for w, _ in windows}
    for row in rows:
        name, kind = consumer_of(row, consumers)
        cost = float(row["cost"] or 0)
        c = per.setdefault(name, {"name": name, "kind": kind, "key_ids": set(), "tx_total": 0, "cost_total": 0.0, "first": row["ts"], "last": row["ts"],
                                   **{f"tx_{w}": 0 for w, _ in windows}, **{f"cost_{w}": 0.0 for w, _ in windows}})
        c["tx_total"] += 1
        c["cost_total"] += cost
        c["last"] = max(c["last"], row["ts"])
        if row["key_id"]:
            c["key_ids"].add(row["key_id"])
        age = now - row["ts"]
        for w, span in windows:
            if age <= span:
                c[f"tx_{w}"] += 1
                c[f"cost_{w}"] += cost
                totals[w]["tx"] += 1
                totals[w]["cost"] += cost
        day = datetime.fromtimestamp(row["ts"], tz=timezone.utc).date().isoformat()
        if day in days:
            d = days[day]
            d["tx"] += 1
            d["cost"] += cost
            d["by"][name] = d["by"].get(name, 0.0) + cost
    # Tagesverbrauch: Mittel der letzten sieben Tage, bei juengerer Historie ueber die vorhandene Spanne.
    span_days = min(7.0, max((now - rows[0]["ts"]) / DAY, 1.0)) if rows else 7.0
    per_day_7d = totals["7d"]["cost"] / span_days
    span_30 = min(30.0, max((now - rows[0]["ts"]) / DAY, 1.0)) if rows else 30.0
    per_day_30d = totals["30d"]["cost"] / span_30
    usable = max(0.0, balance - reserve)

    def runway(amount: float) -> tuple[float | None, str | None]:
        if per_day_7d <= 0:
            return None, None
        d = amount / per_day_7d
        return round(d, 1), _iso(int(now + d * DAY)) if d < 36500 else None

    pause_days, pause_on = runway(usable)
    empty_days, empty_on = runway(balance)
    out_consumers = []
    for c in sorted(per.values(), key=lambda x: (-x["cost_30d"], -x["cost_total"])):
        out_consumers.append({
            "name": c["name"], "kind": c["kind"], "key_ids": sorted(c["key_ids"]),
            **{f"tx_{w}": c[f"tx_{w}"] for w, _ in windows}, **{f"cost_{w}": round(c[f"cost_{w}"], 8) for w, _ in windows},
            "tx_total": c["tx_total"], "cost_total": round(c["cost_total"], 8),
            "per_day_7d": round(c["cost_7d"] / span_days, 8),
            "share_30d": round(c["cost_30d"] / totals["30d"]["cost"], 4) if totals["30d"]["cost"] > 0 else 0.0,
            "first": _iso(c["first"]), "last": _iso(c["last"]),
        })
    out_days = [{"day": d["day"], "tx": d["tx"], "cost": round(d["cost"], 8), "by": {k: round(v, 8) for k, v in sorted(d["by"].items(), key=lambda kv: -kv[1])}} for d in days.values()]
    recent = [{"time": _iso(r["ts"]), "txid": r["txid"], "cost": round(float(r["cost"] or 0), 8), "consumer": consumer_of(r, consumers)[0],
               "name": r["name"], "note": r["note"], "route": r["route"]} for r in rows[-25:][::-1]]
    return {
        "generated": _iso(now),
        "unit": "DOI",
        "wallet": {"balance": round(balance, 8), "pending": round(pending, 8), "reserve": reserve, "usable": round(usable, 8), "public_poe_available": balance >= reserve},
        "burn": {"last_24h": round(totals["24h"]["cost"], 8), "tx_24h": totals["24h"]["tx"], "per_day_7d": round(per_day_7d, 8), "per_day_30d": round(per_day_30d, 8),
                 "tx_per_day_7d": round(totals["7d"]["tx"] / span_days, 1), "cost_30d": round(totals["30d"]["cost"], 8), "tx_30d": totals["30d"]["tx"]},
        "runway": {"basis": "per_day_7d", "public_pause_days": pause_days, "public_pause_on": pause_on, "empty_days": empty_days, "empty_on": empty_on},
        "consumers": out_consumers,
        "days": out_days,
        "deposits": [{"time": _iso(d["ts"]), "amount": round(float(d["amount"]), 8), "txid": d["txid"], "address": d["address"], "label": d["label"]} for d in deposits],
        "deposits_total": {"amount": round(float(deposit_total["s"]), 8), "count": deposit_total["n"]},
        "recent": recent,
        "ledger": {"transactions": len(rows), "waiting_for_wallet": open_rows, "keyed_since": _iso(first_api),
                   "spent_total": round(sum(float(r["cost"] or 0) for r in rows), 8)},
    }
