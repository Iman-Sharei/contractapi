"""Shared test helpers."""

from __future__ import annotations

import pytest

from contractapi.core.config import get_settings

DATA_KEY = "test-data-key-0123456789"
KEY_HEADERS = {"X-API-Key": DATA_KEY}


@pytest.fixture
def data_key(monkeypatch):
    """A configured data-plane API key (APIs that allow changes cannot be public)."""
    monkeypatch.setenv("DATA_API_KEYS", DATA_KEY)
    get_settings.cache_clear()
    yield DATA_KEY
    get_settings.cache_clear()
