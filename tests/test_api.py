"""Tests der Antwort-Auswertung (ohne Netzwerk)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# api.py direkt laden, ohne das Paket (und damit Home Assistant) zu importieren
_spec = importlib.util.spec_from_file_location(
    "ai_usage_api", Path(__file__).parents[1] / "custom_components/ai_usage/api.py"
)
api = importlib.util.module_from_spec(_spec)
sys.modules["ai_usage_api"] = api
_spec.loader.exec_module(api)

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


def test_token_response():
    t = api._parse_token_response({"access_token": "a", "expires_in": 3600}, old_refresh="r")
    assert t.refresh_token == "r"
    try:
        api._parse_token_response({"access_token": "a"})
    except api.AuthError:
        pass
    else:
        raise AssertionError
