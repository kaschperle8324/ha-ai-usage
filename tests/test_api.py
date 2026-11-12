"""Tests der Antwort-Auswertung (ohne Netzwerk)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# api.py direkt laden, ohne das Paket (und damit Home Assistant) zu importieren
_spec = importlib.util.spec_from_file_location(
    "ai_usage_api", Path(__file__).parents[1] / "custom_components/ai_usage/api.py"
)
api = importlib.util.module_from_spec(_spec)
sys.modules["ai_usage_api"] = api
_spec.loader.exec_module(api)

NOW = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)


def test_pkce_url():
    s = api.create_pkce_session()
    q = parse_qs(urlparse(s.url).query)
    assert q["client_id"] == [api.CLAUDE_CLIENT_ID]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == [s.state]
    assert 43 <= len(s.verifier) <= 128


def test_split_code():
    assert api.split_auth_code(" abc#xyz \n") == ("abc", "xyz")
    assert api.split_auth_code("abc") == ("abc", None)


def test_parse_claude():
    data = {
        "five_hour": {"utilization": 6.0, "resets_at": "2025-11-04T04:59:59.943648+00:00"},
        "seven_day": {"utilization": 35.0, "resets_at": "2025-11-06T03:59:59Z"},
        "seven_day_oauth_apps": None,
        "seven_day_opus": {"utilization": 0.0, "resets_at": None},
        "iguana_necktie": None,
        "extra_usage": {"is_enabled": False, "utilization": None},
    }
    r = api.parse_claude_usage(data)
    assert r["five_hour"] == 6.0
    assert r["seven_day"] == 35.0
    assert r["five_hour_resets_at"].tzinfo is not None
    assert r["seven_day_resets_at"].day == 6
    assert r["seven_day_opus"] == 0.0
    assert "seven_day_opus_resets_at" not in r
    assert "seven_day_sonnet" not in r
    assert "extra_usage" not in r


def test_parse_claude_empty():
    assert api.parse_claude_usage({"five_hour": None, "seven_day": None}) == {}


def test_anthropic_cost_and_usage():
    cost = [
        {"starting_at": "2026-11-11T00:00:00Z", "results": [{"amount": "123.5", "currency": "USD"}]},
        {"starting_at": "2026-11-12T00:00:00Z", "results": [{"amount": "50"}, {"amount": "25.5"}]},
    ]
    r = api.parse_anthropic_cost(cost, NOW)
    assert r == {"cost_month": 1.99, "cost_today": 0.755}

    usage = [
        {"starting_at": "2026-11-11T00:00:00Z", "results": [{
            "uncached_input_tokens": 1500,
            "cache_creation": {"ephemeral_1h_input_tokens": 1000, "ephemeral_5m_input_tokens": 500},
            "cache_read_input_tokens": 200,
            "output_tokens": 500,
            "server_tool_use": {"web_search_requests": 10},
        }]},
        {"starting_at": "2026-11-12T00:00:00Z", "results": [{"uncached_input_tokens": 10, "output_tokens": 5}]},
    ]
    u = api.parse_anthropic_usage(usage, NOW)
    assert u == {"input_tokens_month": 3210, "output_tokens_month": 505, "tokens_today": 15}


def test_openai():
    today = int(datetime(2026, 11, 12, tzinfo=UTC).timestamp())
    costs = [
        {"start_time": today - 86400, "results": [{"amount": {"value": 0.5, "currency": "usd"}}]},
        {"start_time": today, "results": [{"amount": {"value": 0.25, "currency": "usd"}}]},
    ]
    assert api.parse_openai_costs(costs, NOW) == {"cost_month": 0.75, "cost_today": 0.25, "currency": "USD"}
    usage = [
        {"start_time": today - 86400, "results": [{"input_tokens": 100, "output_tokens": 50, "num_model_requests": 3}]},
        {"start_time": today, "results": [{"input_tokens": 10, "output_tokens": 5, "num_model_requests": 1}]},
        {"start_time": today, "results": []},
    ]
    assert api.parse_openai_usage(usage, NOW) == {
        "input_tokens_month": 110, "output_tokens_month": 55, "tokens_today": 15, "requests_month": 4,
    }


def test_mistral():
    data = {
        "currency": "eur",
        "chat": {"models": {"mistral-large": {"input": {"value": 1000, "price": 0.2}, "output": {"value": 50, "price": 0.3}}}},
        "ocr": {"models": []},
        "prices": [{"price": 99}],
        "vibe_usage": 0,
        "date": "2026-11-12T00:00:00Z",
    }
    r = api.parse_mistral_usage(data)
    assert r["cost_month"] == 0.5
    assert r["currency"] == "EUR"
    assert r["categories"] == {"chat": 0.5}


def test_token_response():
    t = api._parse_token_response({"access_token": "a", "expires_in": 3600}, old_refresh="r")
    assert t.refresh_token == "r"
    try:
        api._parse_token_response({"access_token": "a"})
    except api.AuthError:
        pass
    else:
        raise AssertionError
