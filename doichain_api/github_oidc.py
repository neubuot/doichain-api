"""Pruefung von GitHub-Actions-OIDC-Tokens fuer das Doichain-Siegel.

Ein Workflow mit `permissions: id-token: write` holt sich bei GitHub ein kurzlebiges JWT (RS256), das
Repository, Ref, Commit und Workflow-Lauf bezeugt. Die API prueft Signatur (JWKS von GitHub, eine Stunde
zwischengespeichert), Aussteller, Zielgruppe (audience) und Ablauf. So braucht kein Repository einen
Schluessel, und das Kontingent zaehlt je Repository."""

import asyncio
import logging
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient, PyJWKClientError

from .config import settings

logger = logging.getLogger("doichain_api.github")

JWKS_URL = settings.github_oidc_issuer + "/.well-known/jwks"
JWKS_TTL_SECONDS = 3600


class OidcError(Exception):
    """Token fehlt, ist abgelaufen, falsch signiert oder fuer eine andere Zielgruppe ausgestellt."""


@dataclass(frozen=True)
class GithubIdentity:
    repository: str          # owner/name
    owner: str
    name: str
    ref: str                 # refs/tags/v1.2.3 oder refs/heads/main
    ref_type: str            # tag oder branch
    sha: str                 # Commit, 40 Hex
    run_id: str
    workflow: str
    event: str
    visibility: str          # public, private, internal

    @property
    def short_ref(self) -> str:
        for prefix in ("refs/tags/", "refs/heads/"):
            if self.ref.startswith(prefix):
                return self.ref[len(prefix):]
        return self.ref

    @property
    def run_url(self) -> str:
        return f"https://github.com/{self.repository}/actions/runs/{self.run_id}"


class _Jwks:
    """JWKS von GitHub mit Zwischenspeicher. PyJWKClient holt die Schluessel selbst nach, wenn eine
    unbekannte Schluesselkennung (kid) auftaucht, ein Neustart des Dienstes leert den Speicher."""

    def __init__(self) -> None:
        self._client = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=JWKS_TTL_SECONDS, timeout=10)

    def signing_key(self, token: str):
        return self._client.get_signing_key_from_jwt(token).key


_jwks = _Jwks()


def _str(claims: dict, key: str) -> str:
    value = claims.get(key)
    return value if isinstance(value, str) else ""


async def verify_github_token(token: str) -> GithubIdentity:
    """Token pruefen und die Identitaet des Workflow-Laufs liefern. Fehler werden als OidcError gemeldet,
    der Text ist englisch, weil ihn Entwickler weltweit in ihrem Workflow-Protokoll lesen."""
    token = (token or "").strip()
    if not token or token.count(".") != 2:
        raise OidcError("Missing or malformed GitHub OIDC token. Add 'permissions: id-token: write' to the job")
    try:
        # Netzzugriff auf GitHub (JWKS) blockierend, deshalb im Thread, damit die Event-Schleife frei bleibt.
        key = await asyncio.to_thread(_jwks.signing_key, token)
    except PyJWKClientError as exc:
        raise OidcError(f"Could not fetch GitHub signing keys: {exc}")
    except OSError as exc:
        raise OidcError(f"Could not reach GitHub to verify the token: {exc}")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.seal_audience,
            issuer=settings.github_oidc_issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,
        )
    except jwt.ExpiredSignatureError:
        raise OidcError("GitHub OIDC token has expired, request a fresh one in the same job step")
    except jwt.InvalidAudienceError:
        raise OidcError(f"GitHub OIDC token was issued for another audience, request it with audience '{settings.seal_audience}'")
    except jwt.InvalidTokenError as exc:
        raise OidcError(f"GitHub OIDC token is invalid: {exc}")
    repository = _str(claims, "repository")
    if "/" not in repository:
        raise OidcError("GitHub OIDC token carries no repository claim")
    owner, _, name = repository.partition("/")
    sha = _str(claims, "sha").lower()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise OidcError("GitHub OIDC token carries no commit sha")
    return GithubIdentity(
        repository=repository,
        owner=owner,
        name=name,
        ref=_str(claims, "ref"),
        ref_type=_str(claims, "ref_type"),
        sha=sha,
        run_id=_str(claims, "run_id"),
        workflow=_str(claims, "workflow"),
        event=_str(claims, "event_name"),
        visibility=_str(claims, "repository_visibility"),
    )
