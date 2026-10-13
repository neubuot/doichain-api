"""Asynchroner JSON-RPC-Client fuer Doichain Core (Bitcoin-Core-kompatibel)."""

import itertools
from decimal import Decimal
from typing import Any

import httpx

from .config import settings


class RPCError(Exception):
    """Fehler, den der Doichain-Daemon selbst gemeldet hat."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NodeUnavailable(Exception):
    """Die Node ist nicht erreichbar oder antwortet nicht mit JSON."""


class DoichainRPC:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        # Lesetimeout bewusst unter dem nginx-Limit (120 s), damit die JSON-Fehlermeldung der API
        # den Client erreicht und nicht die HTML-504-Seite von nginx.
        self._client = httpx.AsyncClient(
            auth=(settings.rpc_user, settings.rpc_password),
            timeout=httpx.Timeout(90.0, connect=5.0),
            headers={"content-type": "application/json"},
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(self, method: str, *params: Any, wallet: bool = False, named: dict[str, Any] | None = None) -> Any:
        """Einen RPC-Aufruf absetzen. wallet=True adressiert das konfigurierte Wallet.
        named=... sendet benannte Parameter als JSON-Objekt (Bitcoin Core akzeptiert beides)."""
        if self._client is None:
            await self.start()
        assert self._client is not None
        url = settings.rpc_url
        if wallet:
            url = url.rstrip("/") + f"/wallet/{settings.rpc_wallet}"
        payload = {"jsonrpc": "1.0", "id": next(self._ids), "method": method, "params": named if named is not None else list(params)}
        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise NodeUnavailable(f"Node nicht erreichbar: {exc.__class__.__name__}") from exc
        if response.status_code == 401:
            raise NodeUnavailable("RPC-Anmeldung an der Node fehlgeschlagen (Benutzer/Passwort pruefen)")
        try:
            data = response.json()
        except ValueError as exc:
            raise NodeUnavailable(f"Node antwortete mit HTTP {response.status_code} ohne JSON") from exc
        if data.get("error"):
            err = data["error"]
            raise RPCError(int(err.get("code", -1)), str(err.get("message", "unbekannter RPC-Fehler")))
        return data.get("result")


rpc = DoichainRPC()


def to_decimal(value: Any) -> Decimal:
    """Betraege aus RPC-Antworten (float) verlustarm in Decimal mit 8 Stellen wandeln."""
    return Decimal(str(value)).quantize(Decimal("0.00000001"))
