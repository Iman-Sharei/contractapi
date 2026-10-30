"""Live Postgres e2e — skips if DATABASE_URL unreachable."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from dataapi.application.data_api_builder import create_data_app
from dataapi.core.config import get_settings
from dataapi.domain.models.spec import parse_spec
from dataapi.infrastructure.db.engine import create_pg_engine
from dataapi.infrastructure.security.jwt_tokens import issue_token
from dataapi.interfaces.http.app_factory import create_studio_app

DB_URL = "postgresql://postgres:postgres@localhost:5433/app"


def _db_available() -> bool:
    try:
        engine = create_pg_engine(DB_URL, pooled=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Demo Postgres not running on :5433")


@pytest.fixture
def customers_spec():
    return parse_spec(
        {
            "database": {"url": DB_URL},
            "app": {
                "title": "E2E",
                "read_only": True,
                "auth": "api_key",
                "rbac": [
                    {"role": "api_client", "endpoints": {"customers": ["id", "name", "email", "created_at"]}}
                ],
            },
            "endpoints": [
                {
                    "name": "customers",
                    "path": "/customers",
                    "table": "customers",
                    "methods": ["GET"],
                    "fields": ["id", "name", "email", "created_at"],
                    "filters": ["email"],
                    "sortable": ["id"],
                    "pagination": {"mode": "cursor", "default_limit": 2, "max_limit": 10},
                    "relations": [
                        {
                            "name": "orders",
                            "table": "orders",
                            "type": "one_to_many",
                            "local_key": "id",
                            "foreign_key": "customer_id",
                            "fields": ["id", "customer_id", "total", "status"],
                            "max_per_parent": 20,
                        }
                    ],
                }
            ],
        }
    )


def test_cursor_pagination_and_relations(customers_spec, monkeypatch):
    monkeypatch.setenv("DATA_API_KEYS", "e2e-key")
    get_settings.cache_clear()
    app = create_data_app(customers_spec)
    client = TestClient(app)
    headers = {"X-API-Key": "e2e-key"}

    page1 = client.get("/v1/customers?limit=2", headers=headers)
    assert page1.status_code == 200, page1.text
    body = page1.json()
    assert body["pagination"]["mode"] == "cursor"
    assert len(body["items"]) == 2
    assert "orders" in body["items"][0]
    assert isinstance(body["items"][0]["orders"], list)
    assert "password_hash" not in body["items"][0]
    assert body["next_cursor"]

    page2 = client.get(f"/v1/customers?limit=2&cursor={body['next_cursor']}", headers=headers)
    assert page2.status_code == 200
    assert len(page2.json()["items"]) >= 1
    get_settings.cache_clear()


def test_jwt_rbac_field_filter(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "dev-jwt-secret-change-me-please-32chars")
    get_settings.cache_clear()
    spec = parse_spec(
        {
            "database": {"url": DB_URL},
            "app": {
                "auth": "jwt",
                "read_only": True,
                "rbac": [
                    {"role": "viewer", "endpoints": {"customers": ["id", "name"]}},
                    {
                        "role": "analyst",
                        "endpoints": {"customers": ["id", "name", "email", "created_at"]},
                    },
                ],
            },
            "endpoints": [
                {
                    "name": "customers",
                    "path": "/customers",
                    "table": "customers",
                    "fields": ["id", "name", "email", "created_at"],
                    "roles": ["viewer", "analyst"],
                    "pagination": {"mode": "offset", "default_limit": 5, "max_limit": 10},
                }
            ],
        }
    )
    app = create_data_app(spec)
    client = TestClient(app)

    viewer = issue_token(subject="v", roles=["viewer"], jwt_cfg=spec.app.jwt)
    res = client.get("/v1/customers", headers={"Authorization": f"Bearer {viewer}"})
    assert res.status_code == 200
    item = res.json()["items"][0]
    assert set(item.keys()) <= {"id", "name"}

    denied = issue_token(subject="x", roles=["other"], jwt_cfg=spec.app.jwt)
    res2 = client.get("/v1/customers", headers={"Authorization": f"Bearer {denied}"})
    assert res2.status_code == 403
    get_settings.cache_clear()


def test_studio_activate_mount(monkeypatch):
    monkeypatch.setenv("DATA_API_KEYS", "e2e-key")
    get_settings.cache_clear()
    studio = TestClient(create_studio_app())
    key = get_settings().studio_api_key
    payload = {
        "check_db": True,
        "spec": {
            "database": {"url": DB_URL},
            "app": {"auth": "api_key", "read_only": True},
            "endpoints": [
                {
                    "name": "customers",
                    "path": "/customers",
                    "table": "customers",
                    "fields": ["id", "name", "email"],
                    "pagination": {"mode": "offset"},
                }
            ],
        },
    }
    act = studio.post("/studio/activate", headers={"X-API-Key": key}, json=payload)
    assert act.status_code == 200, act.text
    data = studio.get("/data/v1/customers", headers={"X-API-Key": "e2e-key"})
    assert data.status_code == 200, data.text
    assert "items" in data.json()
    assert studio.get("/data/ready").status_code == 200
    assert "dataapi_http_requests_total" in studio.get("/data/metrics").text
    get_settings.cache_clear()
