"""API-Schluessel-Pruefung. Drei Stufen: read (Lesen), write (Namen und PoE schreiben),
admin (Wallet-Auszahlungen, generischer RPC). Schluessel kommen per Header
X-API-Key oder Authorization: Bearer <key>. Beide Wege sind als OpenAPI-Sicherheitsschema
deklariert, damit /docs den Authorize-Dialog anbietet."""

import secrets

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

# poe: eingeschraenkter Schluessel fuer die oeffentliche PoE-Web-App (darf nur Nachweise anlegen, mit Tageskontingent)
LEVELS = {"read": 1, "poe": 2, "write": 3, "admin": 4}

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    scheme_name="ApiKey",
    description="API-Schluessel der Stufe poe, write oder admin (Lesen geht ohne Schluessel, solange DOI_PUBLIC_READ=true)",
)
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="Bearer",
    description="Alternativ derselbe Schluessel als Authorization: Bearer <schluessel>",
)


def _same(candidate: str, key: str) -> bool:
    """Zeitkonstanter Vergleich auf Byte-Ebene, damit auch Nicht-ASCII-Zeichen keinen Fehler ausloesen."""
    return secrets.compare_digest(candidate.encode("utf-8"), key.encode("utf-8", "surrogateescape"))


def key_level(key: str | None) -> int:
    """0 = kein gueltiger Schluessel, sonst Stufe des Schluessels."""
    if not key or len(key) > 256:
        return 0
    for candidate in settings.admin_keys:
        if _same(candidate, key):
            return LEVELS["admin"]
    for candidate in settings.write_keys:
        if _same(candidate, key):
            return LEVELS["write"]
    for candidate in settings.poe_keys:
        if _same(candidate, key):
            return LEVELS["poe"]
    for candidate in settings.read_keys:
        if _same(candidate, key):
            return LEVELS["read"]
    return 0


def require(level: str):
    """FastAPI-Dependency, die die geforderte Stufe erzwingt und die erreichte Stufe liefert."""
    needed = LEVELS[level]

    async def dependency(
        request: Request,
        api_key: str | None = Security(api_key_header),
        bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    ) -> int:
        # Nur gewoehnliche Leerzeichen und Tabs abschneiden, geschuetzte Leerzeichen bleiben Kopierfehler.
        key = (api_key or "").strip(" \t") or (bearer.credentials.strip(" \t") if bearer and bearer.credentials else "")
        have = key_level(key or None)
        if needed == LEVELS["read"] and settings.public_read:
            request.state.key_level = max(have, 1)
            return request.state.key_level
        if have >= needed:
            request.state.key_level = have
            return have
        if have == 0:
            raise HTTPException(
                status_code=401,
                detail="API-Schluessel fehlt oder ist ungueltig (Header X-API-Key oder Authorization: Bearer)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(status_code=403, detail=f"Dieser Aufruf braucht einen Schluessel der Stufe '{level}'")

    return dependency
