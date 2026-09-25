"""Tageskontingent fuer die oeffentliche PoE-Web-App (Schluesselstufe poe).

Der Schluessel der Web-App ist im Browser sichtbar, deshalb begrenzt die API, wie viele Nachweise
damit je IP-Adresse und insgesamt pro Tag entstehen duerfen. Zaehler liegen in einer kleinen
SQLite-Datei im StateDirectory des Dienstes, damit beide uvicorn-Worker dieselben Zahlen sehen."""

import os
import sqlite3
import threading
from datetime import datetime, timezone

from .config import settings

_lock = threading.Lock()


class QuotaExceeded(Exception):
    pass


def _today() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(settings.state_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(settings.state_dir, "quota.db"), timeout=5)
    conn.execute("create table if not exists poe_usage (day text not null, ip text not null, n integer not null, primary key (day, ip))")
    return conn


def usage(ip: str) -> dict:
    """Aktuelle Zaehlerstaende fuer eine IP-Adresse (UTC-Tag)."""
    day = _today()
    with _lock, _connect() as conn:
        row = conn.execute("select n from poe_usage where day = ? and ip = ?", (day, ip)).fetchone()
        total = conn.execute("select coalesce(sum(n), 0) from poe_usage where day = ?", (day,)).fetchone()[0]
    used_ip = int(row[0]) if row else 0
    return {
        "day_utc": day,
        "per_ip_day": settings.poe_public_per_ip_day,
        "per_day": settings.poe_public_per_day,
        "used_ip": used_ip,
        "used_total": int(total),
        "remaining_ip": max(0, settings.poe_public_per_ip_day - used_ip),
        "remaining_total": max(0, settings.poe_public_per_day - int(total)),
    }


def register(ip: str) -> dict:
    """Einen Nachweis fuer die IP-Adresse zaehlen oder QuotaExceeded werfen."""
    day = _today()
    with _lock, _connect() as conn:
        row = conn.execute("select n from poe_usage where day = ? and ip = ?", (day, ip)).fetchone()
        used_ip = int(row[0]) if row else 0
        total = int(conn.execute("select coalesce(sum(n), 0) from poe_usage where day = ?", (day,)).fetchone()[0])
        if used_ip >= settings.poe_public_per_ip_day:
            raise QuotaExceeded(f"Tageskontingent dieser Adresse erschoepft ({settings.poe_public_per_ip_day} Nachweise je Tag). Morgen wieder oder mit eigenem write-Schluessel")
        if total >= settings.poe_public_per_day:
            raise QuotaExceeded(f"Tageskontingent der oeffentlichen App erschoepft ({settings.poe_public_per_day} Nachweise je Tag). Morgen wieder oder mit eigenem write-Schluessel")
        conn.execute("insert into poe_usage (day, ip, n) values (?, ?, 1) on conflict(day, ip) do update set n = n + 1", (day, ip))
        conn.execute("delete from poe_usage where day < ?", (day,))
    return usage(ip)
