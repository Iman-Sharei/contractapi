from fastapi.testclient import TestClient

from contractapi.application.data_api_builder import create_data_app
from contractapi.core.config import get_settings
from contractapi.domain.models.spec import parse_spec
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.idempotency import idempotency_store


def _write_spec(db_url: str = "postgresql://postgres:postgres@localhost:5433/app"):
    return parse_spec(
        {
            "database": {"url": db_url},
            "app": {
                "read_only": False,
                "auth": "none",
                "api_prefix": "/v1",
                "cache": {"enabled": True, "ttl_seconds": 60},
                "idempotency": {"enabled": True, "required_for_writes": False},
            },
            "endpoints": [
                {
                    "name": "customers",
                    "path": "/customers",
                    "table": "customers",
                    "methods": ["GET", "POST", "PATCH", "DELETE"],
                    "fields": ["id", "name", "email", "created_at"],
                    "writable_fields": ["name", "email"],
                    "pagination": {"mode": "offset", "default_limit": 20, "max_limit": 50},
                }
            ],
        }
    )


def test_api_prefix_versioning_and_metrics():
    # Use sqlite-less path: only check routing shape without DB for /health/metrics
    # Health does not need DB; metrics always available.
    # For versioned routes we need DB — skip body if unavailable via try.
    from contractapi.infrastructure.db.engine import create_pg_engine
    from sqlalchemy import text

    try:
        engine = create_pg_engine(
            "postgresql://postgres:postgres@localhost:5433/app", pooled=False
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        import pytest

        pytest.skip("Postgres demo unavailable")

    get_settings.cache_clear()
    response_cache.clear()
    app = create_data_app(_write_spec())
    client = TestClient(app)
    assert client.get("/health").json()["api_prefix"] == "/v1"
    assert client.get("/ready").status_code == 200
    listed = client.get("/v1/customers")
    assert listed.status_code == 200
    assert client.get("/customers").status_code == 404
    metrics_body = client.get("/metrics").text
    assert "contractapi_http_requests_total" in metrics_body


def test_idempotency_replay_and_conflict():
    from contractapi.infrastructure.db.engine import create_pg_engine
    from sqlalchemy import text
    import uuid

    try:
        engine = create_pg_engine(
            "postgresql://postgres:postgres@localhost:5433/app", pooled=False
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        import pytest

        pytest.skip("Postgres demo unavailable")

    get_settings.cache_clear()
    response_cache.clear()
    idempotency_store.clear()

    app = create_data_app(_write_spec())
    client = TestClient(app)
    email = f"idem-{uuid.uuid4().hex[:8]}@example.com"
    headers = {"Idempotency-Key": f"key-{uuid.uuid4().hex}"}
    body = {"name": "Idem User", "email": email}

    first = client.post("/v1/customers", json=body, headers=headers)
    assert first.status_code == 201, first.text
    second = client.post("/v1/customers", json=body, headers=headers)
    assert second.status_code == 201
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert second.json()["id"] == first.json()["id"]

    conflict = client.post(
        "/v1/customers",
        json={"name": "Other", "email": f"other-{uuid.uuid4().hex[:8]}@example.com"},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_cache_hit_on_second_get():
    from contractapi.infrastructure.db.engine import create_pg_engine
    from sqlalchemy import text
    from contractapi.infrastructure.observability import metrics

    try:
        engine = create_pg_engine(
            "postgresql://postgres:postgres@localhost:5433/app", pooled=False
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        import pytest

        pytest.skip("Postgres demo unavailable")

    get_settings.cache_clear()
    response_cache.clear()
    app = create_data_app(_write_spec())
    client = TestClient(app)
    assert client.get("/v1/customers").status_code == 200
    assert client.get("/v1/customers").status_code == 200
    rendered = metrics.render_prometheus()
    assert "contractapi_cache_hits_total" in rendered
