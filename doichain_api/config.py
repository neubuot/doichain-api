"""Konfiguration der Doichain REST API. Alle Werte kommen aus Umgebungsvariablen
(siehe /etc/doichain-api/doichain-api.env). Keine Zugangsdaten im Code."""

import os
from dataclasses import dataclass, field


def _csv(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(",") if v.strip())


def _bool(value: str, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "ja", "on")


@dataclass(frozen=True)
class Settings:
    rpc_url: str = os.environ.get("DOI_RPC_URL", "http://127.0.0.1:8339/")
    rpc_user: str = os.environ.get("DOI_RPC_USER", "")
    rpc_password: str = os.environ.get("DOI_RPC_PASSWORD", "")
    rpc_wallet: str = os.environ.get("DOI_RPC_WALLET", "doichain")
    electrum_host: str = os.environ.get("DOI_ELECTRUM_HOST", "127.0.0.1")
    electrum_port: int = int(os.environ.get("DOI_ELECTRUM_PORT", "50001"))
    explorer_url: str = os.environ.get("DOI_EXPLORER_URL", "https://doi-explorer.le-space.de").rstrip("/")
    public_read: bool = _bool(os.environ.get("DOI_PUBLIC_READ"), True)
    read_keys: tuple[str, ...] = field(default_factory=lambda: _csv(os.environ.get("DOI_API_KEYS_READ", "")))
    write_keys: tuple[str, ...] = field(default_factory=lambda: _csv(os.environ.get("DOI_API_KEYS_WRITE", "")))
    admin_keys: tuple[str, ...] = field(default_factory=lambda: _csv(os.environ.get("DOI_API_KEYS_ADMIN", "")))
    # Schluessel der oeffentlichen PoE-Web-App: darf nur Nachweise anlegen, mit Tageskontingent je IP und gesamt.
    poe_keys: tuple[str, ...] = field(default_factory=lambda: _csv(os.environ.get("DOI_API_KEYS_POE", "")))
    poe_public_per_ip_day: int = int(os.environ.get("DOI_POE_PUBLIC_PER_IP_DAY", "10"))
    poe_public_per_day: int = int(os.environ.get("DOI_POE_PUBLIC_PER_DAY", "200"))
    state_dir: str = os.environ.get("DOI_STATE_DIR", "/var/lib/doichain-api")
    poe_prefix: str = os.environ.get("DOI_POE_PREFIX", "poe/")
    max_upload_bytes: int = int(os.environ.get("DOI_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    # Sicherheits-Fork vom September 2026: erster Block, der nur auf der Doichain-Kette existiert.
    fork_height: int = 431018
    fork_hash: str = "71d50ff12b090561cc918ddb560334b4350758c7eace3f058dd332fb112f4b67"
    # Namecoin-Grenzen, die Doichain Core 31 erbt.
    max_name_length: int = 255
    max_value_length: int = 520
    api_version: str = "1.3.0"


settings = Settings()


def _check_keys() -> None:
    """Beim Start abbrechen, wenn ein konfigurierter Schluessel unbrauchbar ist (Tippfehler in der
    Umgebungsdatei), statt spaeter jeden Aufruf mit Schluessel scheitern zu lassen."""
    for name, keys in (("DOI_API_KEYS_READ", settings.read_keys), ("DOI_API_KEYS_POE", settings.poe_keys), ("DOI_API_KEYS_WRITE", settings.write_keys), ("DOI_API_KEYS_ADMIN", settings.admin_keys)):
        for key in keys:
            if not key.isascii() or any(c.isspace() for c in key):
                raise RuntimeError(f"{name}: Schluessel enthaelt Nicht-ASCII-Zeichen oder Leerzeichen, bitte korrigieren")
            if len(key) < 16:
                raise RuntimeError(f"{name}: Schluessel ist kuerzer als 16 Zeichen, bitte mit 'openssl rand -hex 24' erzeugen")


_check_keys()
