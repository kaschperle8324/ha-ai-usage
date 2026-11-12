"""HTTP-Client für die Auslastung des Claude-Abos.

Dieses Modul hat bewusst keine Abhängigkeit zu Home Assistant, damit die
Auswertung der Antworten eigenständig getestet werden kann.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import aiohttp

USER_AGENT = "ha-ai-usage/1.1"
TIMEOUT = aiohttp.ClientTimeout(total=30)


class ApiError(Exception):
    """Allgemeiner Fehler beim Abruf."""


class AuthError(ApiError):
    """Zugangsdaten ungültig oder abgelaufen."""


class RateLimitError(ApiError):
    """Anbieter hat die Anfrage wegen zu vieler Abrufe abgelehnt."""


def _num(value: Any) -> float:
    """Zahl aus int, float oder Dezimal-String lesen, sonst 0."""
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: Any = None,
) -> Any:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        async with session.request(
            method, url, headers=hdrs, json=json, timeout=TIMEOUT
        ) as resp:
            if resp.status in (401, 403):
                text = await resp.text()
                raise AuthError(f"{resp.status}: {text[:200]}")
            if resp.status == 429:
                raise RateLimitError("429: zu viele Anfragen")
            if resp.status >= 400:
                text = await resp.text()
                raise ApiError(f"{resp.status}: {text[:200]}")
            return await resp.json(content_type=None)
    except aiohttp.ClientError as err:
        raise ApiError(f"Verbindungsfehler: {err}") from err
    except TimeoutError as err:
        raise ApiError("Zeitüberschreitung") from err


CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
CLAUDE_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
CLAUDE_TOKEN_URLS = (
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
)
CLAUDE_SCOPES = "user:profile user:inference"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_BETA = "oauth-2025-04-20"

# Bekannte Zeitfenster im Abo-Endpunkt (Schlüssel -> Kurzname)
CLAUDE_WINDOWS = {
    "five_hour": "five_hour",
    "seven_day": "seven_day",
    "seven_day_opus": "seven_day_opus",
    "seven_day_sonnet": "seven_day_sonnet",
}


@dataclass
class OAuthTokens:
    """Token-Paar der Claude-Anmeldung."""

    access_token: str
    refresh_token: str
    expires_at: float  # Unix-Zeit in Sekunden


@dataclass
class PkceSession:
    """Daten einer laufenden Anmeldung."""

    verifier: str
    state: str
    url: str


def create_pkce_session() -> PkceSession:
    """Anmelde-URL mit PKCE erzeugen."""
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "code": "true",
            "client_id": CLAUDE_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": CLAUDE_REDIRECT_URI,
            "scope": CLAUDE_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return PkceSession(verifier=verifier, state=state, url=f"{CLAUDE_AUTHORIZE_URL}?{query}")


def split_auth_code(raw: str) -> tuple[str, str | None]:
    """Eingefügten Code der Form 'code#state' zerlegen."""
    raw = raw.strip()
    if "#" in raw:
        code, state = raw.split("#", 1)
        return code.strip(), state.strip() or None
    return raw, None


def _parse_token_response(data: dict[str, Any], old_refresh: str | None = None) -> OAuthTokens:
    access = data.get("access_token")
    if not access:
        raise AuthError("Antwort enthält kein access_token")
    refresh = data.get("refresh_token") or old_refresh
    if not refresh:
        raise AuthError("Antwort enthält kein refresh_token")
    expires_in = _num(data.get("expires_in")) or 3600
    return OAuthTokens(access, refresh, time.time() + expires_in)


async def _post_token(session: aiohttp.ClientSession, payload: dict[str, str]) -> dict[str, Any]:
    last: ApiError | None = None
    for url in CLAUDE_TOKEN_URLS:
        try:
            return await _request(
                session,
                "POST",
                url,
                headers={"Content-Type": "application/json", "anthropic-beta": CLAUDE_BETA},
                json=payload,
            )
        except AuthError:
            raise
        except ApiError as err:
            last = err
    raise last or ApiError("Token-Endpunkt nicht erreichbar")


async def claude_exchange_code(
    session: aiohttp.ClientSession, pkce: PkceSession, raw_code: str
) -> OAuthTokens:
    """Autorisierungscode gegen Token tauschen."""
    code, state = split_auth_code(raw_code)
    data = await _post_token(
        session,
        {
            "grant_type": "authorization_code",
            "code": code,
            "state": state or pkce.state,
            "client_id": CLAUDE_CLIENT_ID,
            "redirect_uri": CLAUDE_REDIRECT_URI,
            "code_verifier": pkce.verifier,
        },
    )
    return _parse_token_response(data)


async def claude_refresh(session: aiohttp.ClientSession, refresh_token: str) -> OAuthTokens:
    """Zugriffstoken erneuern. Das Refresh-Token kann dabei rotieren."""
    data = await _post_token(
        session,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLAUDE_CLIENT_ID,
        },
    )
    return _parse_token_response(data, old_refresh=refresh_token)


async def claude_fetch_usage(session: aiohttp.ClientSession, access_token: str) -> dict[str, Any]:
    """Rohdaten der Abo-Auslastung abrufen."""
    return await _request(
        session,
        "GET",
        CLAUDE_USAGE_URL,
        headers={"Authorization": f"Bearer {access_token}", "anthropic-beta": CLAUDE_BETA},
    )


def parse_claude_usage(data: dict[str, Any]) -> dict[str, Any]:
    """Abo-Antwort in flache Werte umwandeln.

    Ergebnis z. B. {"five_hour": 12.0, "five_hour_resets_at": datetime, ...}
    """
    result: dict[str, Any] = {}
    for key, name in CLAUDE_WINDOWS.items():
        window = data.get(key)
        if not isinstance(window, dict) or window.get("utilization") is None:
            continue
        result[name] = round(_num(window.get("utilization")), 1)
        reset = window.get("resets_at")
        if reset:
            try:
                result[f"{name}_resets_at"] = datetime.fromisoformat(
                    str(reset).replace("Z", "+00:00")
                )
            except ValueError:
                pass
    extra = data.get("extra_usage")
    if isinstance(extra, dict):
        if extra.get("utilization") is not None:
            result["extra_usage"] = round(_num(extra.get("utilization")), 1)
        for src, dst in (("used_credits", "extra_used"), ("monthly_limit", "extra_limit")):
            if extra.get(src) is not None:
                result[dst] = _num(extra.get(src))
    return result
