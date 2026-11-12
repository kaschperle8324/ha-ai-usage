"""Konstanten für die Integration AI Usage."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ai_usage"
VERSION: Final = "1.0.0"

CONF_PROVIDER: Final = "provider"
CONF_ADMIN_KEY: Final = "admin_key"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_EXPIRES_AT: Final = "expires_at"
CONF_SCAN_INTERVAL: Final = "scan_interval"

PROVIDER_CLAUDE_SUB: Final = "claude_subscription"
PROVIDER_ANTHROPIC_API: Final = "anthropic_api"
PROVIDER_OPENAI_API: Final = "openai_api"
PROVIDER_MISTRAL_API: Final = "mistral_api"

PROVIDER_TITLES: Final = {
    PROVIDER_CLAUDE_SUB: "Claude Abo",
    PROVIDER_ANTHROPIC_API: "Anthropic API",
    PROVIDER_OPENAI_API: "OpenAI API",
    PROVIDER_MISTRAL_API: "Mistral API",
}

# Abfrageintervalle in Minuten. Der Abo-Endpunkt ist streng rate-limitiert,
# die Kosten-Endpunkte aktualisieren sich ohnehin nur verzögert.
DEFAULT_SCAN_MINUTES: Final = {
    PROVIDER_CLAUDE_SUB: 10,
    PROVIDER_ANTHROPIC_API: 30,
    PROVIDER_OPENAI_API: 30,
    PROVIDER_MISTRAL_API: 60,
}
MIN_SCAN_MINUTES: Final = 5
MAX_SCAN_MINUTES: Final = 240

# Abstand vor Ablauf, ab dem das Zugriffstoken erneuert wird
TOKEN_REFRESH_MARGIN: Final = timedelta(minutes=5)
