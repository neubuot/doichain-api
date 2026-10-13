"""Tageskontingent fuer Nachweise mit poe-Schluessel.

Der Schluessel der oeffentlichen Web-App ist im Browser sichtbar, deshalb begrenzt die API, wie viele Nachweise
damit je IP-Adresse und insgesamt pro Tag entstehen duerfen. Schluessel mit eigenem Kontingent
(DOI_POE_KEY_LIMITS) zaehlen stattdessen je Schluessel, unabhaengig von der IP-Adresse, mit einer gemeinsamen
Tagesgrenze (DOI_POE_KEYED_PER_DAY). Zaehler liegen in einer kleinen SQLite-Datei im StateDirectory des
Dienstes, damit beide uvicorn-Worker dieselben Zahlen sehen.

Die Zaehler-Identitaet ist entweder die IP-Adresse (Bereich "ip"), "key:<fingerprint>" (Bereich "key") oder
"gh:<owner/repo>" (Bereich "gh", Siegel fuer Software-Releases ueber GitHub Actions, gezaehlt je Repository).
Gesamtsummen werden je Bereich gebildet, Nachweise mit Schluesselkontingent belasten also nicht das
Kontingent der oeffentlichen App und umgekehrt."""

import os
import sqlite3
import threading
from datetime import datetime, timezone

from .config import settings

_lock = threading.Lock()
KEY_PREFIX = "key:"
GH_PREFIX = "gh:"


class QuotaExceeded(Exception):
    pass


def _today() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def _scope(ident: str) -> str:
    if ident.startswith(KEY_PREFIX):
        return "key"
    if ident.startswith(GH_PREFIX):
        return "gh"
    return "ip"


def _connect() -> sqlite3.Connection:
    os.makedirs(settings.state_dir, exist_ok=True)
    # isolation_level=None: eigene Transaktionssteuerung, BEGIN IMMEDIATE serialisiert Pruefen und Zaehlen
    # ueber alle uvicorn-Worker hinweg (die Datei-Sperre wartet bis timeout).
    conn = sqlite3.connect(os.path.join(settings.state_dir, "quota.db"), timeout=5, isolation_level=None)
    conn.execute("create table if not exists poe_usage (day text not null, ip text not null, n integer not null, primary key (day, ip))")
    return conn


def _total(conn: sqlite3.Connection, day: str, scope: str) -> int:
    """Summe des Tages im selben Bereich (IP-Adressen oder Schluessel)."""
    row = conn.execute(
        "select coalesce(sum(n), 0) from poe_usage where day = ? and "
        "(case when substr(ip, 1, ?) = ? then 'key' when substr(ip, 1, ?) = ? then 'gh' else 'ip' end) = ?",
        (day, len(KEY_PREFIX), KEY_PREFIX, len(GH_PREFIX), GH_PREFIX, scope),
    ).fetchone()
    return int(row[0])


def release(ident: str) -> None:
    """Einen zuvor gezaehlten Nachweis zurueckgeben, wenn die Verankerung danach fehlgeschlagen ist."""
    day = _today()
    with _lock, _connect() as conn:
        conn.execute("update poe_usage set n = n - 1 where day = ? and ip = ? and n > 0", (day, ident))


def usage(ident: str, *, per_ip_day: int | None = None, per_day: int | None = None) -> dict:
    """Aktuelle Zaehlerstaende fuer eine IP-Adresse oder einen Schluessel (UTC-Tag).

    *per_ip_day* ist die Grenze der einzelnen Identitaet (bei Schluesseln das Tageskontingent des Schluessels),
    *per_day* die gemeinsame Grenze des Bereichs. Beide ueberschreiben die Standardwerte aus der Konfiguration."""
    if per_ip_day is None:
        per_ip_day = settings.poe_public_per_ip_day
    if per_day is None:
        per_day = settings.poe_public_per_day
    day = _today()
    scope = _scope(ident)
    with _lock, _connect() as conn:
        row = conn.execute("select n from poe_usage where day = ? and ip = ?", (day, ident)).fetchone()
        total = _total(conn, day, scope)
    used = int(row[0]) if row else 0
    return {
        "day_utc": day,
        "scope": scope,
        "per_ip_day": per_ip_day,
        "per_day": per_day,
        "used_ip": used,
        "used_total": total,
        "remaining_ip": max(0, per_ip_day - used),
        "remaining_total": max(0, per_day - total),
    }


def register(ident: str, *, per_ip_day: int | None = None, per_day: int | None = None) -> dict:
    """Einen Nachweis fuer die Identitaet zaehlen oder QuotaExceeded werfen (Grenzen siehe usage())."""
    if per_ip_day is None:
        per_ip_day = settings.poe_public_per_ip_day
    if per_day is None:
        per_day = settings.poe_public_per_day
    day = _today()
    scope = _scope(ident)
    with _lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("select n from poe_usage where day = ? and ip = ?", (day, ident)).fetchone()
            used = int(row[0]) if row else 0
            total = _total(conn, day, scope)
            if used >= per_ip_day:
                if scope == "gh":
                    raise QuotaExceeded(f"Daily seal quota of this repository is used up ({per_ip_day} seals per day). Try again tomorrow or ask the operator for a higher quota")
                if scope == "key":
                    raise QuotaExceeded(f"Tageskontingent dieses Schluessels erschoepft ({per_ip_day} Nachweise je Tag). Morgen wieder oder Kontingent beim Betreiber erhoehen lassen")
                raise QuotaExceeded(f"Tageskontingent dieser Adresse erschoepft ({per_ip_day} Nachweise je Tag). Morgen wieder oder mit eigenem write-Schluessel")
            if total >= per_day:
                if scope == "gh":
                    raise QuotaExceeded(f"Shared daily seal quota of the GitHub integration is used up ({per_day} seals per day). Try again tomorrow")
                if scope == "key":
                    raise QuotaExceeded(f"Gemeinsames Tageskontingent aller Schluessel erschoepft ({per_day} Nachweise je Tag). Morgen wieder")
                raise QuotaExceeded(f"Tageskontingent der oeffentlichen App erschoepft ({per_day} Nachweise je Tag). Morgen wieder oder mit eigenem write-Schluessel")
            conn.execute("insert into poe_usage (day, ip, n) values (?, ?, 1) on conflict(day, ip) do update set n = n + 1", (day, ident))
            conn.execute("delete from poe_usage where day < ?", (day,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return usage(ident, per_ip_day=per_ip_day, per_day=per_day)
