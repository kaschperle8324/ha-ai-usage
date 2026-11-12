"""Konstanten für die Integration AI Usage."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ai_usage"
VERSION: Final = "1.1.0"

CONF_PROVIDER: Final = "provider"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_EXPIRES_AT: Final = "expires_at"
CONF_SCAN_INTERVAL: Final = "scan_interval"

PROVIDER_CLAUDE_SUB: Final = "claude_subscription"
DEFAULT_TITLE: Final = "Claude Abo"

# Abfrageintervall in Minuten. Der Endpunkt ist streng rate-limitiert.
DEFAULT_SCAN_MINUTES: Final = 10
MIN_SCAN_MINUTES: Final = 5
MAX_SCAN_MINUTES: Final = 240

# Abstand vor Ablauf, ab dem das Zugriffstoken erneuert wird
TOKEN_REFRESH_MARGIN: Final = timedelta(minutes=5)
