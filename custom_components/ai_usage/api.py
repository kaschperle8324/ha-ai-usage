"""HTTP-Clients für die Verbrauchsdaten der KI-Anbieter.

Dieses Modul hat bewusst keine Abhängigkeit zu Home Assistant, damit die
Auswertung der Antworten eigenständig getestet werden kann.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import aiohttp

USER_AGENT = "ha-ai-usage/1.0"
TIMEOUT = aiohttp.ClientTimeout(total=30)


class ApiError(Exception):
    """Allgemeiner Fehler beim Abruf."""


class AuthError(ApiError):
    """Zugangsdaten ungültig oder abgelaufen."""


class RateLimitError(ApiError):
    """Anbieter hat die Anfrage wegen zu vieler Abrufe abgelehnt."""


def month_start(now: datetime | None = None) -> datetime:
    """Beginn des laufenden Monats (UTC)."""
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def day_start(now: datetime | None = None) -> datetime:
    """Beginn des laufenden Tages (UTC)."""
    now = now or datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    params: Any = None,
    json: Any = None,
) -> Any:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        async with session.request(
            method, url, headers=hdrs, params=params, json=json, timeout=TIMEOUT
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


# ---------------------------------------------------------------------------
# Claude Abo (Pro/Max) – inoffizieller OAuth-Endpunkt
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Anthropic API (Admin API, offiziell)
# ---------------------------------------------------------------------------

ANTHROPIC_BASE = "https://api.anthropic.com/v1/organizations"


def _anthropic_headers(key: str) -> dict[str, str]:
    return {"x-api-key": key, "anthropic-version": "2023-06-01"}


async def _anthropic_paged(
    session: aiohttp.ClientSession, key: str, path: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    page: str | None = None
    for _ in range(20):
        query = dict(params)
        if page:
            query["page"] = page
        data = await _request(
            session, "GET", f"{ANTHROPIC_BASE}/{path}", headers=_anthropic_headers(key), params=query
        )
        buckets.extend(data.get("data") or [])
        if not data.get("has_more") or not data.get("next_page"):
            break
        page = data["next_page"]
    return buckets


def parse_anthropic_cost(buckets: list[dict[str, Any]], today: datetime) -> dict[str, float]:
    """Kosten (Cent-Strings) zu USD summieren – Monat und heute."""
    month = day = 0.0
    today_key = today.strftime("%Y-%m-%d")
    for bucket in buckets:
        cents = sum(_num(r.get("amount")) for r in bucket.get("results") or [])
        month += cents
        if str(bucket.get("starting_at", "")).startswith(today_key):
            day += cents
    return {"cost_month": round(month / 100, 4), "cost_today": round(day / 100, 4)}


def _anthropic_input_tokens(r: dict[str, Any]) -> float:
    cache = r.get("cache_creation") or {}
    return (
        _num(r.get("uncached_input_tokens"))
        + _num(r.get("cache_read_input_tokens"))
        + sum(_num(v) for v in cache.values() if not isinstance(v, dict))
    )


def parse_anthropic_usage(buckets: list[dict[str, Any]], today: datetime) -> dict[str, int]:
    """Token-Summen für Monat und heute."""
    out = {"input_tokens_month": 0.0, "output_tokens_month": 0.0, "tokens_today": 0.0}
    today_key = today.strftime("%Y-%m-%d")
    for bucket in buckets:
        is_today = str(bucket.get("starting_at", "")).startswith(today_key)
        for r in bucket.get("results") or []:
            inp = _anthropic_input_tokens(r)
            outp = _num(r.get("output_tokens"))
            out["input_tokens_month"] += inp
            out["output_tokens_month"] += outp
            if is_today:
                out["tokens_today"] += inp + outp
    return {k: int(v) for k, v in out.items()}


async def anthropic_fetch(session: aiohttp.ClientSession, key: str) -> dict[str, Any]:
    """Kosten und Tokens des laufenden Monats abrufen."""
    now = datetime.now(UTC)
    params = {"starting_at": _iso(month_start(now)), "bucket_width": "1d", "limit": 31}
    cost = await _anthropic_paged(session, key, "cost_report", params)
    usage = await _anthropic_paged(session, key, "usage_report/messages", params)
    result: dict[str, Any] = {"currency": "USD"}
    result.update(parse_anthropic_cost(cost, now))
    result.update(parse_anthropic_usage(usage, now))
    return result


# ---------------------------------------------------------------------------
# OpenAI API (Admin API, offiziell)
# ---------------------------------------------------------------------------

OPENAI_BASE = "https://api.openai.com/v1/organization"


async def _openai_paged(
    session: aiohttp.ClientSession, key: str, path: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    page: str | None = None
    for _ in range(20):
        query = dict(params)
        if page:
            query["page"] = page
        data = await _request(
            session,
            "GET",
            f"{OPENAI_BASE}/{path}",
            headers={"Authorization": f"Bearer {key}"},
            params=query,
        )
        buckets.extend(data.get("data") or [])
        if not data.get("has_more") or not data.get("next_page"):
            break
        page = data["next_page"]
    return buckets


def parse_openai_costs(buckets: list[dict[str, Any]], today: datetime) -> dict[str, Any]:
    """Kosten summieren – Monat und heute."""
    month = day = 0.0
    currency = "USD"
    today_ts = int(day_start(today).timestamp())
    for bucket in buckets:
        total = 0.0
        for r in bucket.get("results") or []:
            amount = r.get("amount") or {}
            total += _num(amount.get("value"))
            if amount.get("currency"):
                currency = str(amount["currency"]).upper()
        month += total
        if int(_num(bucket.get("start_time"))) >= today_ts:
            day += total
    return {"cost_month": round(month, 4), "cost_today": round(day, 4), "currency": currency}


def parse_openai_usage(buckets: list[dict[str, Any]], today: datetime) -> dict[str, int]:
    """Token- und Anfragezahlen summieren."""
    out = {"input_tokens_month": 0.0, "output_tokens_month": 0.0, "tokens_today": 0.0, "requests_month": 0.0}
    today_ts = int(day_start(today).timestamp())
    for bucket in buckets:
        is_today = int(_num(bucket.get("start_time"))) >= today_ts
        for r in bucket.get("results") or []:
            inp = _num(r.get("input_tokens"))
            outp = _num(r.get("output_tokens"))
            out["input_tokens_month"] += inp
            out["output_tokens_month"] += outp
            out["requests_month"] += _num(r.get("num_model_requests"))
            if is_today:
                out["tokens_today"] += inp + outp
    return {k: int(v) for k, v in out.items()}


async def openai_fetch(session: aiohttp.ClientSession, key: str) -> dict[str, Any]:
    """Kosten und Tokens des laufenden Monats abrufen."""
    now = datetime.now(UTC)
    params = {"start_time": int(month_start(now).timestamp()), "bucket_width": "1d", "limit": 31}
    costs = await _openai_paged(session, key, "costs", params)
    usage = await _openai_paged(session, key, "usage/completions", params)
    result = parse_openai_costs(costs, now)
    result.update(parse_openai_usage(usage, now))
    return result


# ---------------------------------------------------------------------------
# Mistral API (Admin API, nur Enterprise) – experimentell
# ---------------------------------------------------------------------------

MISTRAL_BASE = "https://api.mistral.ai/v1/admin"
_MISTRAL_SKIP = {"prices", "date", "start_date", "end_date", "next_month", "previous_month", "vibe_usage"}
_MISTRAL_COST_KEYS = ("price", "cost", "amount")


def _sum_costs(node: Any, inside_cost: bool = False) -> float:
    """Zahlen unter Schlüsseln wie *price*/*cost*/*amount* rekursiv summieren."""
    if isinstance(node, dict):
        total = 0.0
        for key, value in node.items():
            k = str(key).lower()
            is_cost = any(c in k for c in _MISTRAL_COST_KEYS) and "unit" not in k
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if is_cost:
                    total += float(value)
            elif isinstance(value, str) and is_cost:
                total += _num(value)
            else:
                total += _sum_costs(value, inside_cost or is_cost)
        return total
    if isinstance(node, list):
        return sum(_sum_costs(item, inside_cost) for item in node)
    return 0.0


def parse_mistral_usage(data: dict[str, Any]) -> dict[str, Any]:
    """Monatskosten aus der Mistral-Antwort lesen (Struktur nur teilweise dokumentiert)."""
    categories: dict[str, float] = {}
    for key, value in data.items():
        if key in _MISTRAL_SKIP or not isinstance(value, (dict, list)):
            continue
        cost = round(_sum_costs(value), 4)
        if cost:
            categories[key] = cost
    return {
        "cost_month": round(sum(categories.values()), 4),
        "currency": (data.get("currency") or "EUR").upper(),
        "categories": categories,
    }


async def mistral_fetch(session: aiohttp.ClientSession, key: str) -> dict[str, Any]:
    """Verbrauch des laufenden Monats und Ausgabenlimit abrufen."""
    now = datetime.now(UTC)
    headers = {"x-api-key": key}
    usage = await _request(
        session, "GET", f"{MISTRAL_BASE}/usage", headers=headers,
        params={"month": now.month, "year": now.year},
    )
    result = parse_mistral_usage(usage)
    try:
        limits = await _request(session, "GET", f"{MISTRAL_BASE}/spend-limit", headers=headers)
        completion = ((limits or {}).get("limits") or {}).get("completion") or {}
        if "monthly_limit_reached" in completion:
            result["limit_reached"] = bool(completion["monthly_limit_reached"])
    except AuthError:
        raise
    except ApiError:
        pass
    result["raw"] = usage
    return result


async def validate_admin_key(session: aiohttp.ClientSession, provider: str, key: str) -> None:
    """Schlüssel mit einem kleinen Abruf prüfen (wirft AuthError/ApiError)."""
    if provider == "anthropic_api":
        await anthropic_fetch(session, key)
    elif provider == "openai_api":
        await openai_fetch(session, key)
    elif provider == "mistral_api":
        await mistral_fetch(session, key)
