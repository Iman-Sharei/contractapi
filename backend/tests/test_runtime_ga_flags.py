"""OIDC, job queue, and multi-active are GA (no experimental gate)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from contractapi.core.config import Settings, get_settings
from contractapi.infrastructure.security.oidc import oidc_enabled
from contractapi.interfaces.http.app_factory import create_studio_app


def test_legacy_experimental_all_is_noop():
    assert Settings(experimental="all").experimental_set == set()
    assert Settings(experimental="").experimental_set == set()


def test_oidc_enabled_by_issuer_only(monkeypatch):
    monkeypatch.setenv("STUDIO_OIDC_ISSUER", "https://idp.example/realms/x")
    monkeypatch.setenv("CONTRACTAPI_EXPERIMENTAL", "")
    get_settings.cache_clear()
    try:
        assert oidc_enabled(get_settings()) is True
    finally:
        get_settings.cache_clear()


def test_health_reports_ga_surfaces():
    client = TestClient(create_studio_app())
    headers = {"X-API-Key": get_settings().studio_api_key}
    for path in ("/health", "/studio/health"):
        res = client.get(path, headers=headers if path.startswith("/studio") else None)
        assert res.status_code == 200, path
        body = res.json()
        assert body["multi_active"] is True
        assert "oidc" in body
        assert "job_queue" in body
        assert body.get("experimental") == []
