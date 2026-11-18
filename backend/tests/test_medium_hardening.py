"""Regression tests for the Medium hardening phase (audit 2026-11-18: M2, M4–M11)."""

from __future__ import annotations

import base64
import hashlib
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.core.config import get_settings
from contractapi.domain.models.spec import JwtConfig, parse_spec
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.db.engine import create_pg_engine
from contractapi.infrastructure.kv import reset_kv
from contractapi.infrastructure.security.jwt_tokens import issue_token

PG = "postgresql://postgres:postgres@localhost:5433/app"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    get_settings.cache_clear()
    reset_kv()
    response_cache.clear()
    yield
    get_settings.cache_clear()
    reset_kv()


@pytest.fixture
def pg():
    try:
        engine = create_pg_engine(PG, pooled=False)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS med_h CASCADE"))
            conn.execute(text("CREATE SCHEMA med_h"))
            conn.execute(text("CREATE SEQUENCE med_h.seq"))
            conn.execute(text("CREATE TABLE med_h.parents (id serial primary key, owner text, name text)"))
            conn.execute(
                text(
                    "CREATE TABLE med_h.kids (id serial primary key, parent_id int, label text, "
                    "deleted_at timestamptz)"
                )
            )
            conn.execute(text("INSERT INTO med_h.parents(owner,name) VALUES ('a','p1')"))
            conn.execute(
                text(
                    "INSERT INTO med_h.kids(parent_id,label,deleted_at) VALUES "
                    "(1,'k1',NULL),(1,'k2',now()),(1,'k3',NULL),(1,'k4',NULL),(1,'k5',NULL)"
                )
            )
    except Exception:
        pytest.skip("Postgres demo unavailable")
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS med_h CASCADE"))


def _spec(endpoints, **app):
    return parse_spec({"database": {"url": PG}, "app": {"api_prefix": "", "auth": "none", **app}, "endpoints": endpoints})


def _bearer(sub):
    return {"Authorization": f"Bearer {issue_token(subject=sub, roles=['x'], jwt_cfg=JwtConfig())}"}


# --- M8: OIDC -------------------------------------------------------------------


def test_safe_return_to_blocks_open_redirects():
    from contractapi.interfaces.http.studio.oidc_router import safe_return_to

    assert safe_return_to("/studio/ops") == "/studio/ops"
    for bad in ["//evil.com", "/\\evil.com", "https://evil.com", "", None, "/a|b"]:
        assert safe_return_to(bad) == "/studio"


def test_pkce_is_s256():
    from contractapi.infrastructure.security.oidc import pkce_pair

    verifier, challenge = pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == expected.decode()


def test_oidc_requires_audience_or_client_id(monkeypatch):
    from contractapi.infrastructure.security.oidc import oidc_config_problems

    monkeypatch.setenv("STUDIO_OIDC_ISSUER", "https://idp.example")
    get_settings.cache_clear()
    assert oidc_config_problems()
    monkeypatch.setenv("STUDIO_OIDC_CLIENT_ID", "studio")
    get_settings.cache_clear()
    assert oidc_config_problems() == []


@pytest.fixture
def idp(monkeypatch):
    """Fake IdP: RSA key + JWKS client stub; returns a token minting function."""
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    key = crypto.generate_private_key(public_exponent=65537, key_size=2048)
    from contractapi.infrastructure.security import oidc

    monkeypatch.setenv("STUDIO_OIDC_ISSUER", "https://idp.example")
    monkeypatch.setenv("STUDIO_OIDC_CLIENT_ID", "studio")
    monkeypatch.setenv("STUDIO_OIDC_REDIRECT_URI", "http://api/studio/oidc/callback")
    get_settings.cache_clear()
    stub = SimpleNamespace(get_signing_key_from_jwt=lambda _t: SimpleNamespace(key=key.public_key()))
    monkeypatch.setattr(oidc, "_jwks_client", lambda _s: stub)

    def mint(**claims):
        base = {"iss": "https://idp.example", "sub": "u1", "exp": int(time.time()) + 300}
        return pyjwt.encode({**base, **claims}, key, algorithm="RS256")

    return mint


def test_token_for_another_client_is_rejected(idp):
    from contractapi.core.errors import AppError
    from contractapi.infrastructure.security.oidc import verify_studio_oidc_token

    assert verify_studio_oidc_token(idp(aud="studio"))["sub"] == "u1"
    assert verify_studio_oidc_token(idp(aud="api", azp="studio"))["sub"] == "u1"
    with pytest.raises(AppError):
        verify_studio_oidc_token(idp(aud="some-other-app"))


def test_login_sends_pkce_and_nonce_and_callback_checks_nonce(idp, monkeypatch):
    from contractapi.interfaces.http.studio import oidc_router

    monkeypatch.setattr(
        oidc_router, "oidc_discovery", lambda _i: {"authorization_endpoint": "https://idp.example/auth"}
    )
    monkeypatch.setenv("RESTORE_ACTIVE_ON_BOOT", "false")
    get_settings.cache_clear()
    from contractapi.interfaces.http.app_factory import create_studio_app

    client = TestClient(create_studio_app(), follow_redirects=False)
    r = client.get("/studio/oidc/login", params={"return_to": "//evil.com"})
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["nonce"][0] and q["state"][0]

    def callback(nonce: str):
        monkeypatch.setattr(oidc_router, "exchange_code_for_tokens", lambda *a, **k: {"id_token": idp(aud="studio", nonce=nonce)})
        return client.get("/studio/oidc/callback", params={"code": "c", "state": q["state"][0]})

    assert callback("wrong-nonce").status_code == 401
    ok = callback(q["nonce"][0])
    assert ok.status_code == 302
    assert ok.headers["location"].endswith("/studio")  # //evil.com was neutralised


# --- M9: webhook SSRF -----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/h", "http://localhost/h", "ftp://example.com/x"],
)
def test_webhook_to_internal_targets_blocked(url):
    from contractapi.infrastructure.net_guard import BlockedDestination, assert_public_url

    with pytest.raises(BlockedDestination):
        assert_public_url(url)


def test_webhook_private_opt_in_and_public_ok(monkeypatch):
    from contractapi.infrastructure.net_guard import assert_public_url

    assert_public_url("https://93.184.216.34/hook")
    monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE", "true")
    get_settings.cache_clear()
    assert_public_url("http://127.0.0.1/hook")


# --- M4 + M2: read-only SQL, bounded relations ------------------------------------


def test_sql_endpoint_cannot_write_even_via_functions(pg):
    spec = _spec([{"name": "n", "path": "/n", "sql": "SELECT nextval('med_h.seq') AS id", "fields": ["id"], "pagination": {"mode": "offset"}}])
    client = TestClient(create_data_app(spec))
    assert client.get("/n").status_code >= 400
    with pg.connect() as conn:
        assert conn.execute(text("SELECT last_value, is_called FROM med_h.seq")).one() == (1, False)


def test_relations_capped_in_sql_and_hide_deleted(pg):
    spec = _spec(
        [
            {
                "name": "parents",
                "path": "/parents",
                "table": "parents",
                "schema": "med_h",
                "fields": ["id", "name"],
                "pagination": {"mode": "offset"},
                "relations": [
                    {"name": "kids", "table": "kids", "schema": "med_h", "local_key": "id",
                     "foreign_key": "parent_id", "fields": ["id", "label"], "max_per_parent": 2,
                     "soft_delete_column": "deleted_at"}
                ],
            }
        ]
    )
    body = TestClient(create_data_app(spec)).get("/parents/1").json()
    assert [k["label"] for k in body["kids"]] == ["k1", "k3"]


# --- M5: body limit ---------------------------------------------------------------


def test_chunked_body_over_limit_is_413(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "100")
    monkeypatch.setenv("RESTORE_ACTIVE_ON_BOOT", "false")
    get_settings.cache_clear()
    from contractapi.interfaces.http.app_factory import create_studio_app

    client = TestClient(create_studio_app())
    key = get_settings().studio_api_key

    def chunks():
        for _ in range(10):
            yield b"x" * 50

    r = client.post("/studio/validate", content=chunks(), headers={"X-API-Key": key, "content-type": "application/json"})
    assert r.status_code == 413


# --- M7 + M6: idempotency claim, bounded memory KV --------------------------------


def test_idempotency_claim_is_exclusive_and_released_on_failure(pg):
    from contractapi.infrastructure.idempotency import idempotency_store

    assert idempotency_store.claim("k1") is True
    assert idempotency_store.claim("k1") is False
    idempotency_store.release("k1")
    assert idempotency_store.claim("k1") is True

    spec = _spec(
        [{"name": "parents", "path": "/parents", "table": "parents", "schema": "med_h", "methods": ["GET", "POST"],
          "fields": ["id", "owner", "name"], "writable_fields": ["owner", "name"], "pagination": {"mode": "offset"},
          "validations": [{"field": "name", "min_length": 3}]}],
        read_only=False,
    )
    client = TestClient(create_data_app(spec))
    h = {"Idempotency-Key": "same-key"}
    assert client.post("/parents", json={"owner": "a", "name": "x"}, headers=h).status_code == 422
    assert client.post("/parents", json={"owner": "a", "name": "valid"}, headers=h).status_code == 201


def test_memory_kv_is_bounded():
    from contractapi.infrastructure.kv import MemoryKv

    kv = MemoryKv(max_entries=100)
    for i in range(250):
        kv.set(f"k{i}", "v", 60)
    assert len(kv._data) <= 100
    assert kv.get("k249") == "v" and kv.get("k0") is None


# --- M10: job ownership ----------------------------------------------------------


def test_jobs_visible_only_to_their_owner(pg):
    spec = _spec(
        [{"name": "parents", "path": "/parents", "table": "parents", "schema": "med_h", "methods": ["GET", "POST"],
          "fields": ["id", "owner", "name"], "writable_fields": ["owner", "name"], "async_writes": True,
          "pagination": {"mode": "offset"}}],
        read_only=False,
        auth="jwt",
    )
    client = TestClient(create_data_app(spec))
    job_id = client.post("/parents", json={"owner": "a", "name": "async"}, headers=_bearer("alice")).json()["job_id"]
    assert client.get(f"/jobs/{job_id}", headers=_bearer("mallory")).status_code == 404
    assert client.get(f"/jobs/{job_id}", headers=_bearer("alice")).status_code == 200


# --- M11: safe error messages ----------------------------------------------------


def test_db_messages_strip_credentials():
    from contractapi.infrastructure.db.errors import safe_db_message

    msg = safe_db_message(RuntimeError("connect to postgresql://bob:hunter2@db:5432/app failed; password=hunter2\nmore"))
    assert "hunter2" not in msg and "bob" not in msg and "more" not in msg
    assert "failed" in msg


def test_studio_introspect_error_is_actionable_without_secrets(monkeypatch):
    monkeypatch.setenv("RESTORE_ACTIVE_ON_BOOT", "false")
    get_settings.cache_clear()
    from contractapi.interfaces.http.app_factory import create_studio_app

    client = TestClient(create_studio_app())
    r = client.post(
        "/studio/introspect",
        json={"database_url": "postgresql://bob:hunter2@127.0.0.1:1/app"},
        headers={"X-API-Key": get_settings().studio_api_key},
    )
    assert r.status_code == 400
    assert "hunter2" not in r.text
    assert r.json()["detail"].startswith("Could not connect to the database")


# --- Low items: trace ids, activate names, version source --------------------------


def test_trace_id_reused_only_when_well_formed(pg):
    client = TestClient(create_data_app(_spec([{"name": "p", "path": "/p", "table": "parents", "schema": "med_h", "fields": ["id"]}])))
    assert client.get("/health", headers={"X-Trace-Id": "abc12345-req"}).headers["x-trace-id"] == "abc12345-req"
    bad = client.get("/health", headers={"X-Trace-Id": "x" * 500}).headers["x-trace-id"]
    assert bad != "x" * 500 and len(bad) == 32
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    assert client.get("/health", headers={"traceparent": tp}).headers["x-trace-id"] == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_activate_rejects_unsafe_api_names(monkeypatch):
    monkeypatch.setenv("RESTORE_ACTIVE_ON_BOOT", "false")
    get_settings.cache_clear()
    from contractapi.interfaces.http.app_factory import create_studio_app

    client = TestClient(create_studio_app())
    spec = {"database": {"url": PG}, "endpoints": [{"name": "x", "path": "/x", "table": "t", "fields": ["id"]}]}
    r = client.post("/studio/activate/Bad%20Name", json={"spec": spec}, headers={"X-API-Key": get_settings().studio_api_key})
    assert r.status_code == 400
    assert r.json()["type"].endswith("/invalid-name")


def test_health_reports_package_version(monkeypatch):
    import contractapi

    monkeypatch.setenv("RESTORE_ACTIVE_ON_BOOT", "false")
    get_settings.cache_clear()
    from contractapi.interfaces.http.app_factory import create_studio_app

    assert TestClient(create_studio_app()).get("/health").json()["version"] == contractapi.__version__
