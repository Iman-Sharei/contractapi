"""Studio as an organisation needs it: every route behind sign-in, every change in the audit
trail (who, what, no secrets), history that survives restarts, safe environment copies,
public APIs that can only read, and hand-over files that point at the right API."""

from __future__ import annotations

import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

from contractapi.application.client_exports import build_postman_collection, build_python_sdk
from contractapi.core.config import Settings, get_settings
from contractapi.domain.models.spec import parse_spec
from contractapi.interfaces.http.app_factory import create_studio_app

DB = "postgresql://u@db.example.com/app"
EP = {"name": "orders", "path": "/orders", "table": "orders", "fields": ["id", "status", "total"]}


def _spec(**app) -> dict:
    return {"database": {"url": DB}, "app": {"api_prefix": "/v1", **app}, "endpoints": [EP]}


@pytest.fixture
def studio(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    get_settings.cache_clear()
    client = TestClient(create_studio_app(), headers={"X-API-Key": get_settings().studio_api_key})
    yield client
    get_settings.cache_clear()


def _studio_routes() -> list[tuple[str, str]]:
    from contractapi.interfaces.http.studio import router as studio_router

    out: list[tuple[str, str]] = []

    def walk(router, prefix: str = "") -> None:  # type: ignore[no-untyped-def]
        for route in router.routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    out.append((method, prefix + route.path_format))
            elif hasattr(route, "original_router"):  # FastAPI ≥0.120 keeps included routers nested
                walk(route.original_router, prefix + getattr(route.include_context, "prefix", ""))

    walk(studio_router.router)
    return sorted(set(out))


@pytest.mark.parametrize(("method", "path"), _studio_routes())
def test_every_studio_route_requires_sign_in(method, path, monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path))
    get_settings.cache_clear()
    url = path.replace("{name}", "x").replace("{snapshot_id}", "x").replace("{key_id}", "x")
    res = TestClient(create_studio_app()).request(method, url, json={})
    assert res.status_code == 401, f"{method} {path} answered {res.status_code} without a key"
    assert res.headers["content-type"].startswith("application/problem+json")
    get_settings.cache_clear()


def test_studio_changes_are_audited_with_who_and_without_secrets(studio):
    from contractapi.infrastructure.audit import recent_events

    assert studio.post("/studio/specs", json={"name": "shop", "spec": _spec()}).status_code == 200
    key = studio.post("/studio/keys", json={"name": "reporting-app", "apis": ["shop"], "access": "read"}).json()
    assert studio.delete(f"/studio/keys/{key['id']}").status_code == 200
    assert studio.post("/studio/specs/shop/promote", json={"environment": "staging"}).status_code == 200
    assert studio.delete("/studio/specs/shop").status_code == 200

    events = recent_events(50)
    actions = [e["action"] for e in events]
    assert actions == ["studio.spec.save", "studio.key.create", "studio.key.revoke",
                       "studio.spec.promote", "studio.spec.delete"]  # one event per action
    assert {e["sub"] for e in events} == {"studio-key"}  # who did it
    created = next(e for e in events if e["action"] == "studio.key.create")
    assert created["meta"]["name"] == "reporting-app" and created["meta"]["prefix"] == key["prefix"]
    log = json.dumps(events)
    assert key["key"] not in log and get_settings().studio_api_key not in log  # never secrets
    # The Activity page shows the same, in the log's order.
    assert [e["action"] for e in studio.get("/studio/audit").json()["events"]] == actions


def test_activity_survives_a_restart_and_a_half_written_line(studio, tmp_path):
    from contractapi.infrastructure import audit

    for i in range(5):
        audit.audit_event(action="update", api="shop", endpoint="orders", resource_id=i)
    audit._memory.clear()  # a restart forgets the in-memory list
    with (tmp_path / "audit.jsonl").open("a") as fh:
        fh.write('{"action": "upd')  # another process is still writing this line
    events = audit.recent_events(3)
    assert [e["resource_id"] for e in events] == [2, 3, 4]  # newest complete events, in order
    assert all(e["api"] == "shop" for e in events)


def test_promote_keeps_the_target_environments_own_database(studio):
    assert studio.post("/studio/specs", json={"name": "shop", "spec": _spec()}).status_code == 200
    first = studio.post("/studio/specs/shop/promote", json={"environment": "production"}).json()
    assert first["name"] == "shop_production" and first["database_kept"] is False

    prod = studio.get("/studio/specs/shop_production").json()["spec"]
    prod["database"]["url"] = "postgresql://u@prod-db.example.com/app"
    assert studio.post("/studio/specs", json={"name": "shop_production", "spec": prod}).status_code == 200

    newer = _spec()
    newer["endpoints"][0]["fields"] = ["id", "status", "total", "placed_at"]
    assert studio.post("/studio/specs", json={"name": "shop", "spec": newer}).status_code == 200
    again = studio.post("/studio/specs/shop/promote", json={"environment": "production"}).json()
    assert again["database_kept"] is True
    copied = studio.get("/studio/specs/shop_production").json()["spec"]
    assert copied["database"]["url"].startswith("postgresql://u@prod-db.example.com")  # not dev's
    assert copied["endpoints"][0]["fields"][-1] == "placed_at"  # but the new contract
    assert copied["app"]["environment"] == "production"


def test_a_public_api_can_only_read():
    parse_spec(_spec(auth="none"))  # read-only public data is fine
    writes = {**EP, "methods": ["GET", "POST", "DELETE"]}
    with pytest.raises(ValidationError, match="public API can only read data"):
        parse_spec({"database": {"url": DB}, "app": {"auth": "none", "read_only": False}, "endpoints": [writes]})
    parse_spec({"database": {"url": DB}, "app": {"auth": "api_key", "read_only": False}, "endpoints": [writes]})


def test_dbt_schema_yml_is_read_as_yaml_with_its_unique_column_as_id(studio):
    text = """
version: 2
models:
  - name: fct_orders
    columns:
      - name: customer_email
      - name: order_id
        tests: [not_null, unique]
      - name: status
"""
    res = studio.post("/studio/import/dbt", json={"text": text})
    assert res.status_code == 200, res.text
    model = res.json()["endpoints"][0]
    assert model["primary_key"] == "order_id" and model["path"] == "/fct-orders"
    bad = studio.post("/studio/import/dbt", json={"text": "models: [\n  - name: x"})
    assert bad.status_code == 422 and "line" in bad.json()["detail"]
    assert studio.post("/studio/import/dbt", json={"text": "just text"}).status_code == 422


def test_production_refuses_the_default_data_key():
    strong = {"studio_api_key": "s" * 32, "jwt_secret": "j" * 40, "environment": "production"}
    Settings(**strong, data_api_keys="a-long-random-data-key-123").assert_production_safe()
    with pytest.raises(RuntimeError, match="DATA_API_KEYS"):
        Settings(**strong, data_api_keys="dev-data-key").assert_production_safe()


def test_postman_and_sdk_point_at_the_named_api_with_its_auth(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE", "https://api.example.com/")
    get_settings.cache_clear()
    spec = parse_spec({**_spec(read_only=False), "endpoints": [
        {**EP, "methods": ["GET", "POST", "PATCH", "DELETE"], "soft_delete": {"restore": True}}]})
    coll = build_postman_collection(spec, "shop")
    assert coll["variable"][0]["value"] == "https://api.example.com/apis/shop"
    assert coll["auth"]["type"] == "apikey"
    urls = {(r["request"]["method"], r["request"]["url"]["raw"]) for r in coll["item"][0]["item"]}
    assert ("PATCH", "{{baseUrl}}/v1/orders/:id") in urls and ("DELETE", "{{baseUrl}}/v1/orders/:id") in urls
    assert ("POST", "{{baseUrl}}/v1/orders/:id/restore") in urls
    assert not any("/data/" in u for _, u in urls)

    jwt = parse_spec(_spec(auth="jwt"))
    assert build_postman_collection(jwt, "shop")["auth"]["type"] == "bearer"
    sdk = build_python_sdk(jwt, "shop")
    compile(sdk, "shop_sdk.py", "exec")
    assert "CONTRACTAPI_TOKEN" in sdk and "def create_orders" not in sdk  # read-only: no writes
    get_settings.cache_clear()
