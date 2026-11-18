"""Regression tests for the "complete product" phase (audit 2026-11-18: H1–H7, M3, API standards)."""

from __future__ import annotations

import inspect
import os
import stat
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import DatabaseConfig, JwtConfig, parse_spec
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.db.engine import create_engine_for_config, create_pg_engine
from contractapi.infrastructure.security.jwt_tokens import issue_token

PG = "postgresql://postgres:postgres@localhost:5433/app"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    get_settings.cache_clear()
    response_cache.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def pg():
    try:
        engine = create_pg_engine(PG, pooled=False)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS prod_cmp CASCADE"))
            conn.execute(text("CREATE SCHEMA prod_cmp"))
            conn.execute(
                text(
                    "CREATE TABLE prod_cmp.orders (id serial primary key, owner text not null, "
                    "title text, total numeric(10,2), placed_on date, paid boolean default false, "
                    "secret_note text)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO prod_cmp.orders(owner,title,total,placed_on,paid,secret_note) VALUES "
                    "('a','100% cotton',10.50,'2026-01-05',true,'x'),"
                    "('a','plain',250.00,'2026-03-01',false,'y'),"
                    "('b','other',999.00,'2026-03-02',true,'z')"
                )
            )
            conn.execute(
                text("CREATE TABLE prod_cmp.items (id serial primary key, order_id int, sku text)")
            )
            conn.execute(text("INSERT INTO prod_cmp.items(order_id, sku) VALUES (1,'s1'),(1,'s2')"))
    except Exception:  # noqa: BLE001
        pytest.skip("Postgres demo unavailable")
    yield
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS prod_cmp CASCADE"))


def _orders_spec(*, app=None, **ep):
    endpoint = {
        "name": "orders",
        "path": "/orders",
        "table": "orders",
        "schema": "prod_cmp",
        "fields": ["id", "owner", "title", "total", "placed_on", "paid"],
        "filters": ["id", "title", "total", "placed_on", "paid"],
        "sortable": ["id", "total"],
        "pagination": {"mode": "offset"},
        **ep,
    }
    return parse_spec(
        {"database": {"url": PG}, "app": {"api_prefix": "", "auth": "none", **(app or {})}, "endpoints": [endpoint]}
    )


def _bearer(roles):
    return {"Authorization": f"Bearer {issue_token(subject='u', roles=roles, jwt_cfg=JwtConfig())}"}


# --- H1: typed filters ------------------------------------------------------


def test_filters_on_numeric_date_bool_columns(pg):
    c = TestClient(create_data_app(_orders_spec()))

    def ids(**params):
        r = c.get("/orders", params=params)
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert ids(id="2") == [2]
    assert ids(total__gt="100") == [2, 3]
    assert ids(id__in="1,3") == [1, 3]
    assert ids(placed_on__gte="2026-03-01") == [2, 3]
    assert ids(paid="true") == [1, 3]
    assert ids(q="cotton") == [1]  # ?q= skips non-text filter fields instead of 500
    assert ids(title__contains="100%") == [1]  # '%' is literal, not a wildcard


def test_bad_filter_value_is_400_with_guidance(pg):
    c = TestClient(create_data_app(_orders_spec()))
    r = c.get("/orders", params={"placed_on__gte": "yesterday"})
    assert r.status_code == 400
    assert "ISO date" in r.json()["detail"]


def test_sql_endpoint_bad_values_are_client_errors(pg):
    spec = parse_spec(
        {
            "database": {"url": PG},
            "app": {"api_prefix": "", "auth": "none"},
            "endpoints": [
                {
                    "name": "big",
                    "path": "/big",
                    "sql": "SELECT id, total FROM prod_cmp.orders WHERE total > :min",
                    "fields": ["id", "total"],
                    "filters": ["id"],
                    "sql_params": [{"name": "min", "type": "float", "default": 0}],
                    "pagination": {"mode": "offset"},
                }
            ],
        }
    )
    c = TestClient(create_data_app(spec))
    assert c.get("/big", params={"min": "lots"}).status_code == 422
    assert c.get("/big", params={"id": "abc"}).status_code == 400


# --- H2: RBAC on writes / filters / sort -------------------------------------


def test_rbac_applies_to_writes_filters_and_sort(pg):
    spec = _orders_spec(
        app={
            "auth": "jwt",
            "read_only": False,
            "rbac": [{"role": "viewer", "endpoints": {"orders": ["id", "title"]}}],
        },
        methods=["GET", "POST"],
        writable_fields=["owner", "title", "total"],
    )
    c = TestClient(create_data_app(spec))
    h = _bearer(["viewer"])
    created = c.post("/orders", json={"owner": "a", "title": "t", "total": 5}, headers=h)
    assert created.status_code == 201, created.text
    assert set(created.json()) == {"id", "title"}
    assert c.get("/orders", params={"total__gt": "500"}, headers=h).status_code == 400
    assert c.get("/orders", params={"sort": "-total"}, headers=h).status_code == 400


def test_endpoint_roles_enforced_on_writes(pg):
    spec = _orders_spec(
        app={"auth": "jwt", "read_only": False},
        methods=["GET", "POST", "DELETE"],
        writable_fields=["owner", "title"],
        roles=["admin"],
    )
    c = TestClient(create_data_app(spec))
    h = _bearer(["viewer"])
    assert c.post("/orders", json={"owner": "a", "title": "x"}, headers=h).status_code == 403
    assert c.delete("/orders/1", headers=h).status_code == 403


# --- API standards: PUT, Location, ETag ----------------------------------------


def test_put_replaces_and_post_sets_location(pg):
    spec = _orders_spec(
        app={"read_only": False},
        methods=["GET", "POST", "PUT", "PATCH"],
        writable_fields=["owner", "title"],
    )
    c = TestClient(create_data_app(spec))
    created = c.post("/orders", json={"owner": "a", "title": "new"})
    assert created.status_code == 201
    new_id = created.json()["id"]
    assert created.headers["location"] == f"orders/{new_id}"
    partial = c.put(f"/orders/{new_id}", json={"title": "only"})
    assert partial.status_code == 422
    assert partial.json()["missing"] == ["owner"]
    assert c.put(f"/orders/{new_id}", json={"owner": "b", "title": "full"}).status_code == 200
    assert c.patch(f"/orders/{new_id}", json={"title": "partial ok"}).status_code == 200


def test_get_etag_works_for_if_match_with_relations(pg):
    spec = _orders_spec(
        app={"read_only": False},
        methods=["GET", "PATCH"],
        writable_fields=["title"],
        relations=[
            {"name": "items", "table": "items", "schema": "prod_cmp", "local_key": "id",
             "foreign_key": "order_id", "fields": ["id", "sku"]}
        ],
    )
    c = TestClient(create_data_app(spec))
    etag = c.get("/orders/1").headers["etag"]
    r = c.patch("/orders/1", json={"title": "renamed"}, headers={"If-Match": etag})
    assert r.status_code == 200, r.text


# --- H6: URL path rules --------------------------------------------------------


@pytest.mark.parametrize("path", ["/docs/{evil} x'", "/Customers", "/a//b", "/"])
def test_invalid_paths_rejected(path):
    with pytest.raises(ValueError, match="not valid"):
        parse_spec({"database": {"url": PG}, "endpoints": [{"name": "x", "path": path, "table": "t", "fields": ["id"]}]})


def test_reserved_path_only_without_prefix():
    ep = {"name": "metrics", "path": "/metrics", "table": "t", "fields": ["id"]}
    with pytest.raises(ValueError, match="built-in"):
        parse_spec({"database": {"url": PG}, "app": {"api_prefix": ""}, "endpoints": [ep]})
    parse_spec({"database": {"url": PG}, "app": {"api_prefix": "/v1"}, "endpoints": [ep]})


# --- H5: secret store ------------------------------------------------------------


def test_saved_spec_never_contains_the_password(tmp_path):
    from contractapi.infrastructure.persistence import spec_repo
    from contractapi.infrastructure.secrets import get_secret, mask_url, resolve_refs

    raw = {
        "database": {"url": "postgresql://app:s3cr%40t@db:5432/app"},
        "endpoints": [{"name": "x", "path": "/x", "table": "t", "fields": ["id"]}],
    }
    spec = spec_repo.save_spec("shop", raw)
    yaml_text = (tmp_path / "specs" / "shop.yaml").read_text()
    assert "s3cr" not in yaml_text
    assert spec.database.url == "postgresql://app:${secret:db-shop}@db:5432/app"
    assert get_secret("db-shop") == "s3cr%40t"
    secret_file = tmp_path / "specs" / ".secrets" / "db-shop"
    assert stat.S_IMODE(os.stat(secret_file).st_mode) == 0o600
    assert resolve_refs(spec.database.url) == raw["database"]["url"]
    assert mask_url(raw["database"]["url"]) == "postgresql://app:****@db:5432/app"
    # A masked password from a Studio round-trip keeps the stored secret.
    again = spec_repo.save_spec("shop", {**raw, "database": {"url": "postgresql://app:****@db:5432/app"}})
    assert again.database.url == spec.database.url


def test_missing_secret_is_clear_error():
    from contractapi.infrastructure.secrets import resolve_refs

    with pytest.raises(AppError, match="not found"):
        resolve_refs("postgresql://u:${secret:nope}@h/db")


# --- H3: IP allowlist --------------------------------------------------------------


def _req(peer: str, xff: str | None = None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_ip_allowlist_cidr_and_spoofing(monkeypatch):
    from contractapi.infrastructure.security.auth import enforce_ip_allowlist

    enforce_ip_allowlist(_req("10.9.9.9"), ["10.0.0.0/8"])  # real CIDR match
    with pytest.raises(AppError):
        enforce_ip_allowlist(_req("1.1.1.1", xff="10.1.2.3"), ["10.0.0.0/8"])  # spoof ignored
    monkeypatch.setenv("TRUSTED_PROXIES", "192.168.0.0/16")
    get_settings.cache_clear()
    enforce_ip_allowlist(_req("192.168.1.1", xff="10.1.2.3"), ["10.0.0.0/8"])  # via trusted proxy


# --- H4: git browser ---------------------------------------------------------------


@pytest.mark.parametrize("ref", ["--output=/tmp/x", "-p", "HEAD;rm", "a..b"])
def test_git_refs_cannot_be_options(ref):
    from contractapi.application.git_browser import GitBrowserError, _check_ref

    with pytest.raises(GitBrowserError):
        _check_ref(ref)


# --- H7 + M3: no blocking handlers, shared engines -----------------------------------


def test_data_handlers_are_sync_and_engines_shared(pg):
    app = create_data_app(_orders_spec())

    def flatten(routes):
        for r in routes:
            inner = getattr(r, "original_router", None)  # FastAPI wraps include_router()
            yield from flatten(inner.routes) if inner is not None else [r]

    data_routes = [r for r in flatten(app.routes) if getattr(r, "path", "").startswith("/orders")]
    assert data_routes
    assert not any(inspect.iscoroutinefunction(r.endpoint) for r in data_routes)
    cfg = DatabaseConfig(url=PG)
    assert create_engine_for_config(cfg) is create_engine_for_config(cfg)


def test_boot_restore_moves_literal_passwords_out_of_runtime_state(tmp_path, monkeypatch):
    import json

    from contractapi.application.studio_service import spec_store
    from contractapi.infrastructure.runtime_store import active_path, save_active
    from contractapi.interfaces.http.app_factory import _restore_runtime

    monkeypatch.setenv("BOOT_SPEC", "")
    get_settings.cache_clear()
    raw = {
        "database": {"url": "postgresql://app:old-pass@db:5432/app"},
        "endpoints": [{"name": "x", "path": "/x", "table": "t", "fields": ["id"]}],
    }
    save_active("legacy", {"legacy": raw})
    try:
        _restore_runtime()
        persisted = active_path().read_text()
        assert "old-pass" not in persisted
        assert "${secret:db-legacy}" in json.loads(persisted)["specs"]["legacy"]["database"]["url"]
    finally:
        spec_store.clear()
