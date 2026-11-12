"""Testumgebung."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Eigene Integrationen in allen Tests erlauben."""
    yield
