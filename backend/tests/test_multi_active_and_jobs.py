from fastapi.testclient import TestClient

from dataapi.application.jobs import create_job, get_job, run_job
from dataapi.application.studio_service import activate_spec, spec_store
from dataapi.interfaces.http.app_factory import create_studio_app


def setup_function() -> None:
    spec_store.clear()


def teardown_function() -> None:
    spec_store.clear()


def _minimal_spec(title: str = "A") -> dict:
    return {
        "database": {"url": "postgresql://postgres:postgres@localhost:5433/app"},
        "app": {
            "title": title,
            "read_only": True,
            "auth": "none",
            "api_prefix": "/v1",
        },
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


def test_multi_active_list_and_mounts():
    import pytest
    from sqlalchemy import text

    from dataapi.infrastructure.db.engine import create_pg_engine

    try:
        engine = create_pg_engine(
            "postgresql://postgres:postgres@localhost:5433/app", pooled=False
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres demo unavailable")

    activate_spec(_minimal_spec("Primary"), name="alpha", primary=True)
    activate_spec(_minimal_spec("Secondary"), name="beta", primary=False)

    assert sorted(spec_store.all()) == ["alpha", "beta"]
    assert spec_store.active_name == "alpha"

    client = TestClient(create_studio_app())
    listed = client.get("/studio/active/list", headers={"X-API-Key": "dev-studio-key-change-me"})
    assert listed.status_code == 200
    names = {a["name"] for a in listed.json()["apis"]}
    assert names == {"alpha", "beta"}

    primary = client.get("/data/v1/customers?limit=1")
    assert primary.status_code == 200, primary.text

    named = client.get("/apis/beta/v1/customers?limit=1")
    assert named.status_code == 200, named.text

    missing = client.get("/apis/nope/v1/customers")
    assert missing.status_code == 404


def test_job_local_lifecycle():
    job = create_job(kind="demo", payload={"x": 1})

    def work():
        return {"ok": True}

    run_job(job.id, work)
    import time

    for _ in range(50):
        got = get_job(job.id)
        assert got is not None
        if got.status in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert got is not None
    assert got.status == "succeeded"
    assert got.result == {"ok": True}


def test_oidc_disabled_still_accepts_api_key():
    client = TestClient(create_studio_app())
    res = client.get("/studio/health", headers={"X-API-Key": "dev-studio-key-change-me"})
    assert res.status_code == 200

    bad = client.get("/studio/health")
    assert bad.status_code == 401
