"""End-to-end smoke: introspect → save → activate → call data plane."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.studio_service import spec_store
from contractapi.infrastructure.runtime_store import clear_active
from contractapi.interfaces.http.app_factory import create_studio_app


STUDIO = {"X-API-Key": "dev-studio-key-change-me"}
DB = "postgresql://postgres:postgres@localhost:5433/app"


def _pg_or_skip():
    try:
        from contractapi.infrastructure.db.engine import create_pg_engine

        engine = create_pg_engine(DB, pooled=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres demo unavailable")


@pytest.fixture(autouse=True)
def _clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    monkeypatch.setenv("RESTORE_ACTIVE_ON_BOOT", "false")
    monkeypatch.setenv("CONTRACTAPI_EXPERIMENTAL", "all")
    from contractapi.core.config import get_settings

    get_settings.cache_clear()
    spec_store.clear()
    clear_active()
    yield
    spec_store.clear()
    clear_active()
    get_settings.cache_clear()


def test_studio_to_data_smoke():
    _pg_or_skip()
    client = TestClient(create_studio_app())

    intro = client.post(
        "/studio/introspect",
        headers=STUDIO,
        json={"database_url": DB, "schema": "public"},
    )
    assert intro.status_code == 200, intro.text
    assert intro.json()["count"] >= 1

    spec = {
        "database": {"url": DB},
        "app": {"title": "Smoke", "auth": "none", "read_only": True, "api_prefix": "/v1"},
        "endpoints": [
            {
                "name": "customers",
                "path": "/customers",
                "table": "customers",
                "fields": ["id", "name", "email"],
                "primary_key": "id",
                "pagination": {"mode": "offset", "default_limit": 5, "max_limit": 20},
            }
        ],
    }
    saved = client.post("/studio/specs", headers=STUDIO, json={"name": "smoke", "spec": spec})
    assert saved.status_code == 200, saved.text

    act = client.post("/studio/activate", headers=STUDIO, json={"spec": spec, "name": "smoke"})
    assert act.status_code == 200, act.text

    data = client.get("/data/v1/customers?limit=1")
    assert data.status_code == 200, data.text
    assert "items" in data.json()

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json().get("maturity") == "beta"
