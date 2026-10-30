"""Compose the studio control-plane FastAPI application."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from dataapi.application.data_api_builder import create_data_app
from dataapi.application.jobs import start_inline_worker
from dataapi.application.studio_service import spec_store
from dataapi.core.config import get_settings
from dataapi.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    problem_response,
    validation_exception_handler,
)
from dataapi.core.logging import setup_logging
from dataapi.infrastructure.db.engine import create_engine_for_config
from dataapi.interfaces.http.middleware.body_limit import BodySizeLimitMiddleware
from dataapi.interfaces.http.middleware.request_id import RequestIdMiddleware
from dataapi.interfaces.http.middleware.security_headers import SecurityHeadersMiddleware
from dataapi.interfaces.http.studio.router import router as studio_router


def _attach_handlers(app: FastAPI) -> FastAPI:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    return app


class DataPlaneASGI:
    """Lazy ASGI mount: serves the primary ApiSpec under /data."""

    def __init__(self) -> None:
        self._app: ASGIApp | None = None
        self._key: Any = None

    def _ensure(self) -> ASGIApp | None:
        spec = spec_store.active
        if spec is None:
            return None
        key = (spec_store.active_name, id(spec))
        if self._app is None or self._key != key:
            data_app = _attach_handlers(create_data_app(spec))
            self._app = data_app
            self._key = key
        return self._app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path = scope.get("path") or ""
        if path == "/data":
            scope = dict(scope)
            scope["path"] = "/"
        elif path.startswith("/data/"):
            scope = dict(scope)
            scope["path"] = path[len("/data") :] or "/"

        app = self._ensure()
        if app is None:
            body = problem_response(
                type_="https://dataapi.dev/problems/no-active-api",
                title="No active API",
                status=404,
                detail="Activate a specification via POST /studio/activate first.",
            )
            await body(scope, receive, send)
            return
        await app(scope, receive, send)


class MultiApiASGI:
    """
    Multi-tenant OSS MVP: serve each activated named spec under /apis/{name}/...

    Pattern similar to Supabase-per-project / PostgREST multi-schema mounts —
    still one process, many contracts (not multi-org SaaS control plane).
    """

    def __init__(self) -> None:
        self._apps: dict[str, ASGIApp] = {}
        self._rev: Any = None

    def _sync(self) -> None:
        rev = spec_store.revision()
        if rev == self._rev:
            return
        self._rev = rev
        self._apps = {
            name: _attach_handlers(create_data_app(spec)) for name, spec in spec_store.all().items()
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        self._sync()
        path = scope.get("path") or ""
        # Match DataPlaneASGI: TestClient/uvicorn may pass the full /apis/... path.
        if path == "/apis":
            path = "/"
        elif path.startswith("/apis/"):
            path = path[len("/apis") :] or "/"
        rest = path if path.startswith("/") else f"/{path}"
        parts = [p for p in rest.split("/") if p]
        if not parts:
            body = problem_response(
                type_="https://dataapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail="Use /apis/{name}/… — list active names via GET /studio/active/list",
            )
            await body(scope, receive, send)
            return
        name, *tail = parts
        app = self._apps.get(name)
        if app is None:
            body = problem_response(
                type_="https://dataapi.dev/problems/no-active-api",
                title="No active API",
                status=404,
                detail=f"No activated API named '{name}'.",
                extensions={"active": sorted(self._apps)},
            )
            await body(scope, receive, send)
            return
        child = dict(scope)
        child["path"] = ("/" + "/".join(tail)) if tail else "/"
        await app(child, receive, send)


def _restore_runtime() -> None:
    """Reload last activated specs and optional boot YAML."""
    from pathlib import Path

    from dataapi.application.job_handlers import register_default_handlers
    from dataapi.domain.models.spec import load_spec, parse_spec
    from dataapi.infrastructure.runtime_store import load_active

    register_default_handlers()
    settings = get_settings()

    if settings.restore_active_on_boot:
        saved = load_active()
        if saved and saved.get("specs"):
            primary = saved.get("primary")
            for name, raw in saved["specs"].items():
                try:
                    spec = parse_spec(raw)
                    spec_store.set(spec, name=name, primary=False)
                except Exception as exc:  # noqa: BLE001
                    from dataapi.core.logging import get_logger

                    get_logger("dataapi.boot").warning("Skip restore %s: %s", name, exc)
            if primary and spec_store.get(primary):
                spec_store.set(spec_store.get(primary), name=primary, primary=True)  # type: ignore[arg-type]

    boot = (settings.boot_spec or "").strip()
    if boot and Path(boot).is_file():
        try:
            spec = load_spec(Path(boot))
            spec_store.set(spec, name=Path(boot).stem, primary=True)
        except Exception as exc:  # noqa: BLE001
            from dataapi.core.logging import get_logger

            get_logger("dataapi.boot").warning("BOOT_SPEC failed: %s", exc)


def create_studio_app() -> FastAPI:
    settings = get_settings()
    setup_logging(debug=settings.debug)
    _restore_runtime()
    if settings.job_queue_enabled and settings.experimental_enabled("queue"):
        start_inline_worker()

    app = FastAPI(
        title="dataapi Studio",
        version="0.5.0b1",
        description=(
            "Spec-first Postgres → FastAPI control plane (Beta). "
            "Design contracts in Studio, activate, then consume /data "
            "(primary) or /apis/{name} (multi-active)."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-API-Key",
            "X-Request-ID",
            "Idempotency-Key",
        ],
        expose_headers=["X-Request-ID", "Idempotent-Replayed", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)

    _attach_handlers(app)

    app.include_router(studio_router)
    app.mount("/data", DataPlaneASGI())
    if settings.experimental_enabled("multi_active"):
        app.mount("/apis", MultiApiASGI())

    @app.get("/health")
    def root_health() -> dict[str, Any]:
        from dataapi.infrastructure.security.oidc import oidc_enabled

        return {
            "status": "ok",
            "service": settings.app_name,
            "version": "0.5.0b1",
            "maturity": "beta",
            "oidc": oidc_enabled(settings) and settings.experimental_enabled("oidc"),
            "job_queue": bool(
                settings.job_queue_enabled
                and settings.redis_url
                and settings.experimental_enabled("queue")
            ),
            "experimental": sorted(settings.experimental_set),
            "active_apis": len(spec_store.all()),
        }

    @app.get("/ready")
    def root_ready() -> dict[str, Any]:
        spec = spec_store.active
        if spec is None:
            return {"status": "ready", "data_api": "inactive", "database": "n/a"}
        try:
            engine = create_engine_for_config(spec.database, pooled=False)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {
                "status": "ready",
                "data_api": "active",
                "database": "ok",
                "name": spec_store.active_name,
                "active_count": len(spec_store.all()),
            }
        except Exception as exc:
            raise AppError(
                type_="https://dataapi.dev/problems/not-ready",
                title="Not Ready",
                status=503,
                detail=f"Database check failed: {exc.__class__.__name__}",
            ) from exc

    return app
