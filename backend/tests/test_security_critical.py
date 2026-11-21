"""Regression tests for the critical authz fixes (audit 2026-11-18, C2–C5)."""

from __future__ import annotations

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.core.config import Settings, get_settings
from contractapi.domain.models.spec import JwtConfig, parse_spec
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.db.engine import create_pg_engine
from contractapi.infrastructure.security.jwt_tokens import issue_token

PG = "postgresql://postgres:postgres@localhost:5433/app"
SQL_EP = {
    "name": "metric",
    "path": "/metric",
    "sql": "SELECT 1 AS id",
    "fields": ["id"],
    "pagination": {"mode": "offset"},
}


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    get_settings.cache_clear()
    response_cache.clear()
    yield
    get_settings.cache_clear()


def _bearer(roles: list[str], **claims) -> dict[str, str]:
    tok = issue_token(subject="u", roles=roles, jwt_cfg=JwtConfig(), extra=claims or None)
    return {"Authorization": f"Bearer {tok}"}


# --- C5: fail closed -------------------------------------------------------


def test_api_key_mode_without_any_key_is_closed(monkeypatch):
    monkeypatch.setenv("DATA_API_KEYS", "")
    get_settings.cache_clear()
    spec = parse_spec({"database": {"url": PG}, "app": {"auth": "api_key"}, "endpoints": [SQL_EP]})
    client = TestClient(create_data_app(spec))
    r = client.get("/v1/metric")
    assert r.status_code == 401
    assert "none is configured" in r.json()["detail"]


def test_api_key_principal_never_contains_the_key(monkeypatch):
    from contractapi.infrastructure.security.auth import authenticate_request

    monkeypatch.setenv("DATA_API_KEYS", "super-secret-data-key")
    get_settings.cache_clear()
    spec = parse_spec({"database": {"url": PG}, "app": {"auth": "api_key"}, "endpoints": [SQL_EP]})

    from types import SimpleNamespace

    req = SimpleNamespace(headers={"X-API-Key": "super-secret-data-key"}, client=None)
    principal = authenticate_request(req, spec)  # type: ignore[arg-type]
    assert "super-secret" not in principal["sub"]


def test_production_refuses_dev_secrets():
    with pytest.raises(RuntimeError, match="production"):
        Settings(environment="production").assert_production_safe()
    Settings(
        environment="production",
        studio_api_key="s" * 24,
        jwt_secret="j" * 40,
        data_api_keys="",  # not from the environment: CI sets a short demo key there
    ).assert_production_safe()


# --- C2: no public token minting ------------------------------------------


def test_no_public_token_endpoint():
    spec = parse_spec({"database": {"url": PG}, "app": {"auth": "jwt"}, "endpoints": [SQL_EP]})
    client = TestClient(create_data_app(spec))
    r = client.post("/auth/token", json={"sub": "x", "roles": ["admin"]})
    assert r.status_code in {401, 404, 405}
    assert "access_token" not in r.text


def test_extra_claims_cannot_override_reserved_claims():
    tok = issue_token(
        subject="u",
        roles=["viewer"],
        jwt_cfg=JwtConfig(),
        extra={"roles": ["admin"], "exp": 4102444800, "sub": "root", "tenant": "A"},
    )
    claims = pyjwt.decode(tok, options={"verify_signature": False})
    assert claims["roles"] == ["viewer"]
    assert claims["sub"] == "u"
    assert claims["exp"] < 4102444800
    assert claims["tenant"] == "A"


# --- C4 + C3: need the demo Postgres ---------------------------------------


@pytest.fixture
def pg_docs():
    try:
        engine = create_pg_engine(PG, pooled=False)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS sec_crit CASCADE"))
            conn.execute(text("CREATE SCHEMA sec_crit"))
            conn.execute(
                text(
                    "CREATE TABLE sec_crit.docs (id serial primary key, tenant text not null, "
                    "title text, salary int)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO sec_crit.docs(tenant,title,salary) "
                    "VALUES ('A','a-doc',100),('B','b-doc',999)"
                )
            )
    except Exception:
        pytest.skip("Postgres demo unavailable")
    yield
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS sec_crit CASCADE"))


def _docs_spec(**app):
    return parse_spec(
        {
            "database": {"url": PG},
            "app": {"api_prefix": "", "auth": "jwt", **app},
            "endpoints": [
                {
                    "name": "docs",
                    "path": "/docs-items",
                    "table": "docs",
                    "schema": "sec_crit",
                    "fields": ["id", "tenant", "title", "salary"],
                    "pagination": {"mode": "offset"},
                    "row_level": {"column": "tenant", "claim": "tenant"},
                }
            ],
        }
    )


def test_cache_is_scoped_per_row_level_tenant(pg_docs):
    client = TestClient(create_data_app(_docs_spec()))
    a = client.get("/docs-items", headers=_bearer(["x"], tenant="A")).json()
    b = client.get("/docs-items", headers=_bearer(["x"], tenant="B")).json()
    assert [i["tenant"] for i in a["items"]] == ["A"]
    assert [i["tenant"] for i in b["items"]] == ["B"]


def test_cache_is_scoped_per_api(pg_docs):
    def single(title_filter: str):
        return parse_spec(
            {
                "database": {"url": PG},
                "app": {"api_prefix": "", "auth": "none", "description": title_filter},
                "endpoints": [
                    {
                        "name": "docs",
                        "path": "/docs-items",
                        "sql": f"SELECT id, title FROM sec_crit.docs WHERE tenant = '{title_filter}'",
                        "fields": ["id", "title"],
                        "pagination": {"mode": "offset"},
                    }
                ],
            }
        )

    ns_a, ns_b = single("A").namespace, single("B").namespace
    assert ns_a != ns_b


def test_graphql_ignores_client_claims_and_widened_roles(pg_docs):
    from contractapi.application.graphql_facade import graphql_available

    if not graphql_available():
        pytest.skip("strawberry not installed")
    spec = _docs_spec(
        rbac=[
            {"role": "viewer", "endpoints": {"docs": ["id", "title"]}},
            {"role": "admin", "endpoints": {"docs": ["id", "tenant", "title", "salary"]}},
        ]
    )
    client = TestClient(create_data_app(spec))
    headers = _bearer(["viewer"], tenant="A")

    # `claims` is no longer an argument; `roles` can only narrow.
    bad = client.post(
        "/graphql",
        json={"query": '{ endpoint(name: "docs", claims: {tenant: "B"}) }'},
        headers=headers,
    ).json()
    assert bad.get("errors")

    def query(q: str):
        return client.post("/graphql", json={"query": q}, headers=headers).json()["data"]["endpoint"]

    # Own token: tenant A rows, viewer fields only.
    assert query('{ endpoint(name: "docs") }') == [{"id": 1, "title": "a-doc"}]
    # Asking for a role the token lacks narrows to nothing extra (never widens).
    assert query('{ endpoint(name: "docs", roles: ["admin"]) }') == [{"id": 1}]


def test_graphql_mutation_respects_row_level(pg_docs):
    from contractapi.application.graphql_facade import graphql_available

    if not graphql_available():
        pytest.skip("strawberry not installed")
    spec = parse_spec(
        {
            "database": {"url": PG},
            "app": {"api_prefix": "", "auth": "jwt", "read_only": False},
            "endpoints": [
                {
                    "name": "docs",
                    "path": "/docs-items",
                    "table": "docs",
                    "schema": "sec_crit",
                    "methods": ["GET", "PATCH", "DELETE"],
                    "fields": ["id", "tenant", "title"],
                    "writable_fields": ["title"],
                    "pagination": {"mode": "offset"},
                    "row_level": {"column": "tenant", "claim": "tenant"},
                }
            ],
        }
    )
    client = TestClient(create_data_app(spec))
    headers = _bearer(["x"], tenant="A")
    upd = client.post(
        "/graphql",
        json={"query": 'mutation { updateItem(endpoint: "docs", id: 2, data: {title: "pwned"}) }'},
        headers=headers,
    ).json()
    assert upd.get("errors"), upd
    dele = client.post(
        "/graphql",
        json={"query": 'mutation { deleteItem(endpoint: "docs", id: 2) }'},
        headers=headers,
    ).json()
    assert dele.get("errors"), dele
    with create_pg_engine(PG, pooled=False).connect() as conn:
        title = conn.execute(text("SELECT title FROM sec_crit.docs WHERE id = 2")).scalar_one()
    assert title == "b-doc"


def test_graphql_requires_auth_like_rest(pg_docs):
    from contractapi.application.graphql_facade import graphql_available

    if not graphql_available():
        pytest.skip("strawberry not installed")
    client = TestClient(create_data_app(_docs_spec()))
    r = client.post("/graphql", json={"query": '{ endpoint(name: "docs") }'})
    assert r.status_code == 401
