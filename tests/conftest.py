"""Fixtures shared by all Allen & Heath iDR tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    """Enable loading this custom integration in every test."""
    yield


@pytest.fixture(autouse=True)
def auto_socket_enabled(socket_enabled: None) -> Generator[None]:
    """Allow real sockets in every test.

    The Home Assistant test harness blocks all sockets by default, but these
    tests drive the integration against a fake iDR (``MockIdr``) listening on
    127.0.0.1, so they need real local TCP. Connections stay limited to
    localhost by the harness.
    """
    yield
