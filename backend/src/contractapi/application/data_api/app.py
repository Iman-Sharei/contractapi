"""Build a FastAPI data-plane app from an ApiSpec (runtime, not codegen)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from sqlalchemy import MetaData, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from contractapi.application.data_api.common import (
    logger,
    output_format_for,
)
from contractapi.application.data_api.http_meta import (
    OutputFormatMiddleware,
    _decorate_response,
    _effective_path,
    _ensure_trace,
    _is_public_path,
    _job_owner,
    _record_metrics,
)
from contractapi.application.data_api.mount import _mount_endpoint
from contractapi.application.data_api.openapi_docs import install_openapi
from contractapi.application.jobs import get_job
from contractapi.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    problem_response,
    validation_exception_handler,
)
from contractapi.domain.models.spec import (
    ApiSpec,
    AuthMode,
)
from contractapi.infrastructure.db.engine import create_engine_for_config
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.idempotency import (
    idempotency_store,
)
from contractapi.infrastructure.observability import Timer, metrics
from contractapi.infrastructure.security.auth import (
    authenticate_request,
    client_ip,
)
from contractapi.infrastructure.security.idp import require_login_crypto
from contractapi.infrastructure.security.jwt_tokens import (
    extract_bearer,
    refresh_tokens,
    revoke_token,
)
from contractapi.infrastructure.security.rate_limit import limiter


def create_data_app(spec: ApiSpec, *, engine: Engine | None = None, name: str | None = None) -> FastAPI:
    engine = engine or create_engine_for_config(spec.database)
    metadata = MetaData()
    prefix = spec.app.api_prefix

    app = FastAPI(
        title=spec.app.title,
        version=spec.app.version,
        description=spec.app.description,
    )
    app.state.engine = engine
    app.state.spec = spec
    app.state.api_name = name  # which saved API this is (audit, key scope); None in previews
    install_openapi(app, spec)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    async def database_error_handler(request: Request, exc: Exception) -> Any:
        # Any DB failure that reached here (schema changed, lost connection, …) → Problem Details.
        return await app_error_handler(request, db_error(exc))  # type: ignore[arg-type]

    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_middleware(OutputFormatMiddleware, fmt=output_format_for(spec))

    public_paths = {
        "/health",
        "/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/auth/refresh",
        "/auth/revoke",
    }

    if spec.app.compression:
        from starlette.middleware.gzip import GZipMiddleware

        app.add_middleware(GZipMiddleware, minimum_size=500)

    @app.middleware("http")
    async def data_plane_guards(request: Request, call_next):  # type: ignore[no-untyped-def]
        timer = Timer()
        path = _effective_path(request)
        trace_id = _ensure_trace(request)

        if _is_public_path(path, public_paths):
            response = await call_next(request)
            _decorate_response(response, spec, trace_id, None)
            _record_metrics(request.method, path, response.status_code, timer.seconds())
            return response

        try:
            principal = authenticate_request(request, spec)
            request.state.principal = principal
        except AppError as exc:
            resp = problem_response(
                type_=exc.type,
                title=exc.title,
                status=exc.status,
                detail=exc.detail,
                extensions=exc.extensions,
            )
            _decorate_response(resp, spec, trace_id, None)
            _record_metrics(request.method, path, exc.status, timer.seconds())
            return resp

        rate_info = None
        if spec.app.rate_limit.enabled:
            sub = principal.get("sub")
            # Anonymous callers get a bucket per client IP, not one shared bucket for all.
            client = str(sub) if sub and sub != "anonymous" else f"ip:{client_ip(request)}"
            try:
                rate_info = limiter.check(
                    f"data:{client}", limit=spec.app.rate_limit.requests_per_minute
                )
            except AppError as exc:
                resp = problem_response(
                    type_=exc.type,
                    title=exc.title,
                    status=exc.status,
                    detail=exc.detail,
                    extensions=exc.extensions,
                )
                if "retry_after" in exc.extensions:
                    resp.headers["Retry-After"] = str(exc.extensions["retry_after"])
                resp.headers["X-RateLimit-Limit"] = str(exc.extensions.get("limit", ""))
                resp.headers["X-RateLimit-Remaining"] = "0"
                _decorate_response(resp, spec, trace_id, None)
                _record_metrics(request.method, path, exc.status, timer.seconds())
                return resp

        response = await call_next(request)
        lock = getattr(request.state, "idem_lock", None)
        if lock and response.status_code >= 400:
            idempotency_store.release(lock)  # failed write: let the client retry the same key
        _decorate_response(response, spec, trace_id, rate_info)
        duration = timer.seconds()
        _record_metrics(request.method, path, response.status_code, duration)
        if spec.app.tracing:
            from contractapi.infrastructure.otel_lite import emit_span

            emit_span(
                name=f"{request.method} {path}",
                trace_id=trace_id,
                duration_ms=duration * 1000,
                status_code=response.status_code,
                attributes={"sub": principal.get("sub")},
            )
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f sub=%s trace_id=%s",
            request.method,
            path,
            response.status_code,
            duration * 1000,
            principal.get("sub"),
            trace_id,
        )
        return response

    @app.get("/health", tags=["system"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "read_only": spec.app.read_only,
            "auth": spec.app.auth.value,
            "api_prefix": prefix or "/",
            "version": spec.app.version,
            "endpoints": len(spec.endpoints),
            "cache": spec.app.cache.enabled,
            "idempotency": spec.app.idempotency.enabled,
        }

    @app.get("/ready", tags=["system"])
    def ready() -> dict[str, Any]:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"status": "ready", "database": "ok"}
        except Exception as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/not-ready",
                title="Not Ready",
                status=503,
                detail=f"Database check failed: {exc.__class__.__name__}",
            ) from exc

    @app.get("/metrics", tags=["system"], response_class=PlainTextResponse)
    def prometheus_metrics() -> PlainTextResponse:
        return PlainTextResponse(metrics.render_prometheus(), media_type="text/plain; version=0.0.4")

    if spec.app.auth == AuthMode.JWT and spec.app.jwt.provider == "oidc":
        require_login_crypto()
    if spec.app.auth == AuthMode.JWT and spec.app.jwt.provider == "contractapi":
        # Refresh / revoke exist only for tokens this server signs; a company login server
        # refreshes and revokes its own tokens.
        # No public token minting here: tokens come from your IdP, or from the
        # admin-only Studio endpoint POST /studio/token for testing.

        @app.post("/auth/refresh", tags=["auth"])
        def refresh(body: dict[str, Any]) -> dict[str, Any]:
            token = str(body.get("refresh_token") or "")
            return refresh_tokens(token, spec.app.jwt)

        @app.post("/auth/revoke", tags=["auth"])
        def revoke(request: Request, body: dict[str, Any] | None = None) -> dict[str, bool]:
            token = (body or {}).get("token") or extract_bearer(request.headers.get("Authorization"))
            if not token:
                raise AppError(
                    type_="https://contractapi.dev/problems/validation-error",
                    title="Validation failed",
                    status=422,
                    detail="token required",
                )
            revoke_token(str(token), spec.app.jwt)
            return {"revoked": True}

    @app.get("/jobs/{job_id}", tags=["jobs"], summary="Status of an async write you submitted")
    def job_status(job_id: str, request: Request) -> dict[str, Any]:
        job = get_job(job_id)
        # 404 (not 403) for other callers' jobs: do not reveal that the id exists.
        if not job or (job.owner and job.owner != _job_owner(spec, request)):
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"Job {job_id} not found",
            )
        return {
            "id": job.id,
            "status": job.status,
            "result": job.result,
            "error": job.error,
        }

    prefixes = [prefix]
    if spec.app.legacy_api_prefix and spec.app.legacy_api_prefix != prefix:
        prefixes.append(spec.app.legacy_api_prefix)

    for pfx in prefixes:
        router = APIRouter(prefix=pfx)
        for endpoint in spec.endpoints:
            _mount_endpoint(router, engine, metadata, endpoint, spec, app=app)
        app.include_router(router)

    try:
        from contractapi.application.graphql_facade import mount_graphql

        # GraphQL is GA when strawberry is installed (optional extra).
        mount_graphql(app, engine, spec)
    except Exception as exc:  # noqa: BLE001 — optional facade must never break the REST API
        logger.warning("GraphQL facade not mounted: %s", exc)

    return app
