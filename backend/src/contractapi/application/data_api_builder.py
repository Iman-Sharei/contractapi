"""Build a FastAPI data-plane app from an ApiSpec (runtime, not codegen)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import MetaData, Table, asc, desc, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from contractapi.application.cursor_paging import decode_cursor, encode_cursor
from contractapi.application.jobs import create_job, enqueue_job, get_job
from contractapi.application.query_filters import combine, parse_filters
from contractapi.application.relations import load_relations
from contractapi.application.row_security import apply_security_clauses
from contractapi.application.validation_rules import validate_payload
from contractapi.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    problem_response,
    validation_exception_handler,
)
from contractapi.core.logging import get_logger
from contractapi.domain.models.spec import (
    ApiSpec,
    AuthMode,
    EndpointSpec,
    HttpMethod,
    PaginationMode,
)
from contractapi.infrastructure.audit import audit_event
from contractapi.infrastructure.webhooks import dispatch_webhooks
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.db.engine import create_engine_for_config
from contractapi.infrastructure.idempotency import (
    IdempotentRecord,
    fingerprint_payload,
    idempotency_store,
    make_scope_key,
    serialize_json_body,
)
from contractapi.infrastructure.observability import Timer, metrics
from contractapi.infrastructure.security.auth import authenticate_request, enforce_endpoint_roles
from contractapi.infrastructure.security.jwt_tokens import (
    extract_bearer,
    issue_token_pair,
    refresh_tokens,
    revoke_token,
)
from contractapi.infrastructure.security.rate_limit import limiter

logger = get_logger("contractapi.data")

_SQLA_TO_PY: dict[str, type] = {
    "INTEGER": int,
    "BIGINT": int,
    "SMALLINT": int,
    "NUMERIC": float,
    "DECIMAL": float,
    "REAL": float,
    "DOUBLE": float,
    "FLOAT": float,
    "BOOLEAN": bool,
    "TEXT": str,
    "VARCHAR": str,
    "CHAR": str,
    "UUID": str,
    "DATE": date,
    "TIMESTAMP": datetime,
    "DATETIME": datetime,
    "JSON": dict,
    "JSONB": dict,
}


def _python_type(sa_type: Any) -> type:
    key = type(sa_type).__name__.upper()
    text = str(sa_type).upper()
    for token, py in _SQLA_TO_PY.items():
        if token in key or token in text:
            return py
    return str


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def _row_to_dict(row: Any, fields: list[str]) -> dict[str, Any]:
    mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    return {f: _serialize(mapping.get(f)) for f in fields}


def _project_fields(item: dict[str, Any], fields: list[str], relation_names: list[str]) -> dict[str, Any]:
    out = {k: item[k] for k in fields if k in item}
    for name in relation_names:
        if name in item:
            out[name] = item[name]
    return out


def _json_response(
    content: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(_serialize(content), status_code=status_code, headers=headers or {})


def _bind_path_type(handler: Any, param: str, typ: type) -> None:
    """`from __future__ import annotations` stringifies local aliases like pk_type; bind the real type."""
    handler.__annotations__[param] = typ


def create_data_app(spec: ApiSpec, *, engine: Engine | None = None) -> FastAPI:
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
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    public_paths = {
        "/health",
        "/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/auth/token",
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
            client = str(principal.get("sub") or "anon")
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

    if spec.app.auth == AuthMode.JWT:

        @app.post("/auth/token", tags=["auth"], include_in_schema=True)
        def issue_dev_token(body: dict[str, Any]) -> dict[str, Any]:
            return issue_token_pair(
                subject=str(body.get("sub", "user")),
                roles=list(body.get("roles") or ["analyst"]),
                jwt_cfg=spec.app.jwt,
                extra={k: v for k, v in body.items() if k not in {"sub", "roles", "expires_minutes"}},
            )

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

    @app.get("/jobs/{job_id}", tags=["jobs"])
    def job_status(job_id: str) -> dict[str, Any]:
        job = get_job(job_id)
        if not job:
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
            _mount_endpoint(router, engine, metadata, endpoint, spec)
        app.include_router(router)

    try:
        from contractapi.core.config import get_settings
        from contractapi.application.graphql_facade import mount_graphql

        if get_settings().experimental_enabled("graphql"):
            mount_graphql(app, engine, spec)
    except Exception:  # noqa: BLE001
        pass

    return app


def _ensure_trace(request: Request) -> str:
    incoming = request.headers.get("traceparent") or request.headers.get("X-Trace-Id")
    if incoming and "traceparent" in (request.headers.keys() if False else []):
        pass
    trace_id = request.headers.get("X-Trace-Id")
    if not trace_id and request.headers.get("traceparent"):
        # W3C: version-traceid-spanid-flags
        parts = request.headers.get("traceparent", "").split("-")
        if len(parts) >= 2:
            trace_id = parts[1]
    if not trace_id:
        trace_id = uuid.uuid4().hex
    request.state.trace_id = trace_id
    return trace_id


def _decorate_response(response: Response, spec: ApiSpec, trace_id: str, rate_info: Any) -> None:
    response.headers.setdefault("X-Trace-Id", trace_id)
    if rate_info is not None:
        response.headers.setdefault("X-RateLimit-Limit", str(rate_info.limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(rate_info.remaining))
        response.headers.setdefault("X-RateLimit-Reset", str(rate_info.reset_seconds))
    dep = spec.app.deprecation
    if dep.deprecated:
        response.headers.setdefault("Deprecation", "true")
        if dep.sunset:
            response.headers.setdefault("Sunset", dep.sunset)
        link_parts: list[str] = []
        existing = response.headers.get("Link")
        if existing:
            link_parts.append(existing)
        if dep.link:
            link_parts.append(f'<{dep.link}>; rel="deprecation"')
        if dep.successor:
            link_parts.append(f'<{dep.successor}>; rel="successor-version"')
        if link_parts:
            response.headers["Link"] = ", ".join(link_parts)


def _effective_path(request: Request) -> str:
    path = request.scope.get("path") or request.url.path
    # When mounted under /data without clean stripping, normalize.
    if path == "/data":
        return "/"
    if path.startswith("/data/"):
        return path[len("/data") :]
    return path


def _is_public_path(path: str, public_paths: set[str]) -> bool:
    if path in public_paths:
        return True
    # also allow trailing-slash variants
    if path.endswith("/") and path[:-1] in public_paths:
        return True
    return False


def _record_metrics(method: str, path: str, status: int, duration: float) -> None:
    labels = {"method": method, "path": path, "status": str(status)}
    metrics.incr("contractapi_http_requests_total", labels=labels)
    metrics.observe("contractapi_http_request_duration_seconds", duration, labels={"method": method, "path": path})


def _model_name(name: str) -> str:
    return "".join(part.title() for part in name.split("_"))


def _mount_endpoint(
    router: APIRouter,
    engine: Engine,
    metadata: MetaData,
    endpoint: EndpointSpec,
    spec: ApiSpec,
) -> None:
    if endpoint.is_sql:
        from contractapi.application.sql_endpoint import mount_sql_endpoint

        mount_sql_endpoint(router, engine, endpoint, spec)
        return

    table = Table(
        endpoint.table,
        metadata,
        schema=endpoint.schema_name,
        autoload_with=engine,
    )
    missing = [f for f in endpoint.fields if f not in table.c]
    if missing:
        raise ValueError(
            f"Endpoint '{endpoint.name}': missing columns on "
            f"{endpoint.schema_name}.{endpoint.table}: {', '.join(missing)}"
        )

    tags = [endpoint.name]
    if HttpMethod.GET in endpoint.methods:
        _add_list(router, engine, metadata, table, endpoint, spec, tags)
        _add_detail(router, engine, metadata, table, endpoint, spec, tags)

    if spec.app.read_only:
        return

    item_model, _, write_model = _build_write_models(endpoint, table)
    if HttpMethod.POST in endpoint.methods:
        _add_create(router, engine, table, endpoint, spec, item_model, write_model, tags)
        if endpoint.bulk_enabled:
            _add_bulk(router, engine, table, endpoint, spec, write_model, tags)
    if HttpMethod.PUT in endpoint.methods or HttpMethod.PATCH in endpoint.methods:
        _add_update(router, engine, table, endpoint, spec, item_model, write_model, tags)
    if HttpMethod.DELETE in endpoint.methods:
        _add_delete(router, engine, table, endpoint, spec, tags)


def _cache_prefix(endpoint: EndpointSpec) -> str:
    return f"ep:{endpoint.name}:"


def _invalidate_endpoint_cache(endpoint: EndpointSpec) -> None:
    response_cache.invalidate_prefix(_cache_prefix(endpoint))


def _build_write_models(endpoint: EndpointSpec, table: Table) -> tuple[type[BaseModel], type[BaseModel], type[BaseModel]]:
    read_fields: dict[str, Any] = {}
    for name in endpoint.fields:
        col = table.c[name]
        py = _python_type(col.type)
        read_fields[name] = (py | None, None) if col.nullable and name != endpoint.primary_key else (py, ...)
    item = create_model(
        f"{_model_name(endpoint.name)}Item",
        __config__=ConfigDict(from_attributes=True, extra="allow"),
        **read_fields,
    )
    listing = create_model(f"{_model_name(endpoint.name)}List", items=(list[dict], ...))
    # All writable fields optional so PATCH can send partial bodies;
    # DB NOT NULL / constraints still enforced on insert/update.
    write_fields: dict[str, Any] = {}
    for name in endpoint.writable_fields:
        col = table.c[name]
        py = _python_type(col.type)
        write_fields[name] = (py | None, None)
    write_model = create_model(
        f"{_model_name(endpoint.name)}Write",
        __config__=ConfigDict(extra="forbid"),
        **write_fields,
    )
    return item, listing, write_model


def _visible_fields(spec: ApiSpec, endpoint: EndpointSpec, request: Request) -> list[str]:
    principal = getattr(request.state, "principal", {"roles": []})
    enforce_endpoint_roles(principal, endpoint.roles)
    rbac = spec.rbac_fields_for(endpoint.name, list(principal.get("roles") or []))
    if rbac is None:
        fields = list(endpoint.fields)
    else:
        fields = [f for f in endpoint.fields if f in rbac or f == endpoint.primary_key]
        if endpoint.primary_key in endpoint.fields and endpoint.primary_key not in fields:
            fields = [endpoint.primary_key, *fields]

    # Sparse fieldsets: ?fields=id,name (must be subset of allowed)
    raw = request.query_params.get("fields")
    if raw:
        requested = [f.strip() for f in raw.split(",") if f.strip()]
        allowed = set(fields)
        bad = [f for f in requested if f not in allowed]
        if bad:
            raise AppError(
                type_="https://contractapi.dev/problems/invalid-fields",
                title="Invalid fields",
                status=400,
                detail="Requested fields are not allowed.",
                extensions={"allowed": sorted(allowed), "rejected": bad},
            )
        # keep PK for identity
        if endpoint.primary_key in allowed and endpoint.primary_key not in requested:
            requested = [endpoint.primary_key, *requested]
        fields = requested
    return fields


def _etag_for(item: dict[str, Any], endpoint: EndpointSpec) -> str:
    if endpoint.etag_field and endpoint.etag_field in item:
        raw = f"{endpoint.name}:{item.get(endpoint.primary_key)}:{item.get(endpoint.etag_field)}"
    else:
        raw = json.dumps(item, sort_keys=True, default=str)
    return '"' + hashlib.sha256(raw.encode()).hexdigest()[:16] + '"'


def _check_if_match(request: Request, etag: str) -> None:
    if_match = request.headers.get("If-Match")
    if not if_match:
        return
    candidates = [p.strip() for p in if_match.split(",")]
    if etag not in candidates and "*" not in candidates:
        raise AppError(
            type_="https://contractapi.dev/problems/precondition-failed",
            title="Precondition Failed",
            status=412,
            detail="If-Match does not match current ETag.",
            extensions={"etag": etag},
        )


def _check_if_none_match(request: Request, etag: str) -> bool:
    """Return True if client already has matching representation (304)."""
    if_none = request.headers.get("If-None-Match")
    if not if_none:
        return False
    return etag in [p.strip() for p in if_none.split(",")]


def _pagination_link_header(
    request: Request,
    *,
    mode: PaginationMode,
    limit: int,
    offset: int,
    total: int | None,
    next_cursor: str | None,
) -> str | None:
    links: list[str] = []
    if mode == PaginationMode.CURSOR:
        if next_cursor:
            next_url = str(request.url.include_query_params(cursor=next_cursor, limit=limit))
            links.append(f'<{next_url}>; rel="next"')
    else:
        if total is not None and offset + limit < total:
            next_url = str(request.url.include_query_params(offset=offset + limit, limit=limit))
            links.append(f'<{next_url}>; rel="next"')
        if offset > 0:
            prev = max(0, offset - limit)
            prev_url = str(request.url.include_query_params(offset=prev, limit=limit))
            links.append(f'<{prev_url}>; rel="prev"')
    return ", ".join(links) if links else None


def _fetch_row(
    engine: Engine,
    table: Table,
    endpoint: EndpointSpec,
    request: Request,
    item_id: Any,
) -> dict[str, Any] | None:
    pk = endpoint.primary_key
    clauses = apply_security_clauses([table.c[pk] == item_id], table, endpoint, request)
    stmt = select(*(table.c[f] for f in endpoint.fields)).where(combine(clauses))
    with engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    return _row_to_dict(row, endpoint.fields)


def _inject_row_level(endpoint: EndpointSpec, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = endpoint.row_level
    if not cfg:
        return payload
    principal = getattr(request.state, "principal", {}) or {}
    claims = principal.get("claims") or {}
    value = claims.get(cfg.claim)
    if value is None:
        value = principal.get(cfg.claim)
    if value is None:
        if cfg.required:
            raise AppError(
                type_="https://contractapi.dev/problems/forbidden",
                title="Forbidden",
                status=403,
                detail=f"Missing claim '{cfg.claim}' for row-level write.",
            )
        return payload
    out = dict(payload)
    if cfg.column in out and out[cfg.column] != value:
        raise AppError(
            type_="https://contractapi.dev/problems/forbidden",
            title="Forbidden",
            status=403,
            detail=f"Cannot set '{cfg.column}' to a value other than your claim.",
        )
    out[cfg.column] = value
    return out


def _audit(spec: ApiSpec, action: str, endpoint: EndpointSpec, request: Request, **kwargs: Any) -> None:
    if not spec.app.audit_enabled:
        return
    audit_event(
        action=action,
        endpoint=endpoint.name,
        principal=getattr(request.state, "principal", None),
        **kwargs,
    )


def _add_list(
    router: APIRouter,
    engine: Engine,
    metadata: MetaData,
    table: Table,
    endpoint: EndpointSpec,
    spec: ApiSpec,
    tags: list[str],
) -> None:
    max_limit = endpoint.pagination.max_limit
    default_limit = endpoint.pagination.default_limit
    allowed_sort = set(endpoint.sortable)
    rel_names = [r.name for r in endpoint.relations]
    reserved = {"limit", "offset", "sort", "cursor", "include_total", "fields", "format"}

    async def list_items(
        request: Request,
        limit: int = Query(default=default_limit, ge=1, le=max_limit),
        offset: int = Query(default=0, ge=0),
        cursor: str | None = Query(default=None),
        sort: str | None = Query(default=None),
        include_total: bool = Query(default=False),
    ) -> Any:
        fields = _visible_fields(spec, endpoint, request)
        if not endpoint.pagination.enabled:
            limit, offset, cursor = max_limit, 0, None

        cache_key = (
            f"{_cache_prefix(endpoint)}list:{request.url.query}:fields={','.join(fields)}"
        )
        if spec.app.cache.enabled:
            cached = response_cache.get(cache_key)
            if cached is not None:
                metrics.incr("contractapi_cache_hits_total", labels={"endpoint": endpoint.name})
                headers = {}
                link = cached.get("_link") if isinstance(cached, dict) else None
                body = {k: v for k, v in cached.items() if k != "_link"} if isinstance(cached, dict) else cached
                if link:
                    headers["Link"] = link
                return _json_response(body, headers=headers)
            metrics.incr("contractapi_cache_misses_total", labels={"endpoint": endpoint.name})

        filter_clauses = parse_filters(
            list(request.query_params.multi_items()),
            table=table,
            endpoint=endpoint,
            reserved=reserved,
        )
        filter_clauses = apply_security_clauses(filter_clauses, table, endpoint, request)
        stmt = select(*(table.c[f] for f in endpoint.fields))
        where = combine(filter_clauses)
        if where is not None:
            stmt = stmt.where(where)

        mode = endpoint.pagination.mode
        next_cursor = None
        total = None

        if mode == PaginationMode.CURSOR:
            pk_col = table.c[endpoint.primary_key]
            stmt = stmt.order_by(asc(pk_col))
            if cursor:
                try:
                    cursor_val = decode_cursor(cursor)
                except Exception as exc:
                    raise AppError(
                        type_="https://contractapi.dev/problems/invalid-cursor",
                        title="Invalid cursor",
                        status=400,
                        detail="Cursor could not be decoded.",
                    ) from exc
                stmt = stmt.where(pk_col > cursor_val)
            fetch_limit = limit + 1
            try:
                with engine.connect() as conn:
                    if include_total:
                        count_stmt = select(func.count()).select_from(table)
                        if where is not None:
                            count_stmt = count_stmt.where(where)
                        total = int(conn.execute(count_stmt).scalar_one())
                    rows = conn.execute(stmt.limit(fetch_limit)).fetchall()
            except SQLAlchemyError as exc:
                raise AppError(
                    type_="https://contractapi.dev/problems/database-error",
                    title="Database error",
                    status=500,
                    detail=exc.__class__.__name__,
                ) from exc

            has_more = len(rows) > limit
            rows = rows[:limit]
            items = [_row_to_dict(r, endpoint.fields) for r in rows]
            if has_more and items:
                next_cursor = encode_cursor(items[-1][endpoint.primary_key])
        else:
            if sort:
                descending = sort.startswith("-")
                col_name = sort[1:] if descending else sort
                if col_name not in allowed_sort:
                    raise AppError(
                        type_="https://contractapi.dev/problems/invalid-sort",
                        title="Sort field not allowed",
                        status=400,
                        detail="Only configured sortable fields are accepted.",
                        extensions={"allowed": sorted(allowed_sort), "rejected": col_name},
                    )
                stmt = stmt.order_by(
                    desc(table.c[col_name]) if descending else asc(table.c[col_name])
                )
            try:
                with engine.connect() as conn:
                    count_stmt = select(func.count()).select_from(table)
                    if where is not None:
                        count_stmt = count_stmt.where(where)
                    total = int(conn.execute(count_stmt).scalar_one())
                    rows = conn.execute(stmt.limit(limit).offset(offset)).fetchall()
            except SQLAlchemyError as exc:
                raise AppError(
                    type_="https://contractapi.dev/problems/database-error",
                    title="Database error",
                    status=500,
                    detail=exc.__class__.__name__,
                ) from exc
            items = [_row_to_dict(r, endpoint.fields) for r in rows]

        if endpoint.relations and items:
            try:
                load_relations(engine, metadata, endpoint.relations, items)
            except Exception as exc:
                raise AppError(
                    type_="https://contractapi.dev/problems/relation-error",
                    title="Relation load failed",
                    status=500,
                    detail=str(exc),
                ) from exc

        projected = [_project_fields(i, fields, rel_names) for i in items]
        payload: dict[str, Any] = {
            "items": projected,
            "limit": limit,
            "pagination": {"mode": mode.value},
        }
        if mode == PaginationMode.CURSOR:
            payload["next_cursor"] = next_cursor
            if include_total and total is not None:
                payload["total"] = total
        else:
            payload["offset"] = offset
            payload["total"] = total

        accept = (request.headers.get("accept") or "").lower()
        fmt = request.query_params.get("format")
        if endpoint.csv_export and (fmt == "csv" or "text/csv" in accept):
            from contractapi.application.sql_endpoint import _csv_response

            return _csv_response(projected, fields)
        if endpoint.ndjson_export and (
            fmt == "ndjson" or "application/x-ndjson" in accept or "application/ndjson" in accept
        ):
            from contractapi.application.sql_endpoint import _ndjson_response

            return _ndjson_response(projected, fields)
        if endpoint.parquet_export and (
            fmt == "parquet"
            or "application/vnd.apache.parquet" in accept
            or "application/parquet" in accept
        ):
            from contractapi.application.sql_endpoint import _parquet_response

            return _parquet_response(projected, fields)

        link = _pagination_link_header(
            request,
            mode=mode,
            limit=limit,
            offset=offset,
            total=total,
            next_cursor=next_cursor,
        )
        if spec.app.cache.enabled:
            to_cache = dict(payload)
            if link:
                to_cache["_link"] = link
            response_cache.set(cache_key, to_cache, spec.app.cache.ttl_seconds)

        headers = {}
        if link:
            headers["Link"] = link
        if endpoint.deprecation.deprecated:
            headers["Deprecation"] = "true"
            if endpoint.deprecation.sunset:
                headers["Sunset"] = endpoint.deprecation.sunset
        return _json_response(payload, headers=headers)

    list_items.__name__ = f"list_{endpoint.name}"
    router.add_api_route(
        endpoint.path,
        list_items,
        methods=["GET"],
        tags=tags,
        summary=endpoint.description or f"List {endpoint.name}",
        name=f"list_{endpoint.name}",
    )


def _add_detail(
    router: APIRouter,
    engine: Engine,
    metadata: MetaData,
    table: Table,
    endpoint: EndpointSpec,
    spec: ApiSpec,
    tags: list[str],
) -> None:
    pk = endpoint.primary_key
    pk_type = _python_type(table.c[pk].type)
    rel_names = [r.name for r in endpoint.relations]

    async def get_item(request: Request, item_id: Any) -> Any:
        fields = _visible_fields(spec, endpoint, request)
        cache_key = f"{_cache_prefix(endpoint)}detail:{item_id}:fields={','.join(fields)}"
        cached = None
        if spec.app.cache.enabled:
            cached = response_cache.get(cache_key)
            if cached is not None:
                metrics.incr("contractapi_cache_hits_total", labels={"endpoint": endpoint.name})
            else:
                metrics.incr("contractapi_cache_misses_total", labels={"endpoint": endpoint.name})

        if cached is None:
            try:
                item = _fetch_row(engine, table, endpoint, request, item_id)
            except SQLAlchemyError as exc:
                raise AppError(
                    type_="https://contractapi.dev/problems/database-error",
                    title="Database error",
                    status=500,
                    detail=exc.__class__.__name__,
                ) from exc
            if item is None:
                raise AppError(
                    type_="https://contractapi.dev/problems/not-found",
                    title="Not Found",
                    status=404,
                    detail=f"{endpoint.name} with {pk}={item_id} not found",
                )
            if endpoint.relations:
                load_relations(engine, metadata, endpoint.relations, [item])
            projected = _project_fields(item, fields, rel_names)
            if spec.app.cache.enabled:
                response_cache.set(cache_key, projected, spec.app.cache.ttl_seconds)
        else:
            projected = cached

        etag = _etag_for(projected, endpoint)
        if _check_if_none_match(request, etag):
            return Response(status_code=304, headers={"ETag": etag})
        headers = {"ETag": etag}
        if endpoint.deprecation.deprecated:
            headers["Deprecation"] = "true"
        return _json_response(projected, headers=headers)

    get_item.__name__ = f"get_{endpoint.name}"
    _bind_path_type(get_item, "item_id", pk_type)
    router.add_api_route(
        f"{endpoint.path}/{{item_id}}",
        get_item,
        methods=["GET"],
        tags=tags,
        summary=f"Get {endpoint.name}",
        name=f"get_{endpoint.name}",
    )


def _idempotency_begin(
    request: Request,
    *,
    spec: ApiSpec,
    endpoint: EndpointSpec,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> str | None:
    """Return store key if idempotency applies; may raise AppError or return early Response via exception path.

    If a prior matching record exists, raises AppError with status encoded via a special return using Response
    is awkward — instead return ('replay', Response) pattern. Simpler: return replay Response | None and key.
    """
    cfg = spec.app.idempotency
    if not cfg.enabled:
        return None
    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key:
        if cfg.required_for_writes:
            raise AppError(
                type_="https://contractapi.dev/problems/idempotency-key-required",
                title="Idempotency-Key required",
                status=400,
                detail="Provide Idempotency-Key header for write operations.",
            )
        return None
    if len(idem_key) > 256:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-idempotency-key",
            title="Invalid Idempotency-Key",
            status=400,
            detail="Idempotency-Key must be <= 256 characters.",
        )
    return make_scope_key(f"{endpoint.name}:{method}:{path}", idem_key)


def _idempotency_replay_or_conflict(
    store_key: str,
    *,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> Response | None:
    body = serialize_json_body(payload)
    fp = fingerprint_payload(method, path, body)
    existing = idempotency_store.get(store_key)
    if existing is None:
        return None
    if existing.fingerprint != fp:
        raise AppError(
            type_="https://contractapi.dev/problems/idempotency-conflict",
            title="Idempotency conflict",
            status=409,
            detail="Idempotency-Key was reused with a different payload.",
        )
    headers = {"Idempotent-Replayed": "true", **existing.headers}
    if existing.status_code == 204:
        return Response(status_code=204, headers=headers)
    import json

    return Response(
        content=json.dumps(existing.body, default=str),
        status_code=existing.status_code,
        media_type="application/json",
        headers=headers,
    )


def _idempotency_commit(
    store_key: str | None,
    *,
    method: str,
    path: str,
    payload: dict[str, Any],
    status_code: int,
    body: Any,
    ttl_seconds: int,
) -> None:
    if not store_key:
        return
    idempotency_store.ttl_seconds = ttl_seconds
    idempotency_store.put(
        store_key,
        IdempotentRecord(
            fingerprint=fingerprint_payload(method, path, serialize_json_body(payload)),
            status_code=status_code,
            body=body,
            headers={},
            created_at=__import__("time").monotonic(),
        ),
    )


async def _read_write_body(request: Request, write_model: type[BaseModel]) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="Request body must be JSON.",
        ) from exc
    if not isinstance(raw, dict):
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="Request body must be a JSON object.",
        )
    try:
        return write_model.model_validate(raw).model_dump(exclude_unset=True)
    except Exception as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail=str(exc),
        ) from exc


def _do_insert(engine: Engine, table: Table, endpoint: EndpointSpec, payload: dict[str, Any]) -> dict[str, Any]:
    stmt = table.insert().values(**payload).returning(*(table.c[f] for f in endpoint.fields))
    try:
        with engine.begin() as conn:
            row = conn.execute(stmt).fetchone()
    except IntegrityError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/conflict",
            title="Conflict",
            status=409,
            detail="Insert violated a database constraint.",
        ) from exc
    except SQLAlchemyError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/database-error",
            title="Database error",
            status=500,
            detail=exc.__class__.__name__,
        ) from exc
    return _row_to_dict(row, endpoint.fields)


def _add_create(router, engine, table, endpoint, spec, item_model, write_model, tags) -> None:  # type: ignore[no-untyped-def]
    async def create_item(request: Request) -> Any:
        payload = await _read_write_body(request, write_model)
        validate_payload(endpoint, payload)
        payload = _inject_row_level(endpoint, request, payload)
        path = endpoint.path
        store_key = _idempotency_begin(
            request, spec=spec, endpoint=endpoint, method="POST", path=path, payload=payload
        )
        if store_key:
            replay = _idempotency_replay_or_conflict(store_key, method="POST", path=path, payload=payload)
            if replay is not None:
                return replay

        if endpoint.async_writes:
            job_payload = {
                "database_url": spec.database.url,
                "driver": spec.database.driver.value,
                "table": endpoint.table,
                "schema": endpoint.schema_name,
                "fields": endpoint.fields,
                "primary_key": endpoint.primary_key,
                "endpoint_name": endpoint.name,
                "path": endpoint.path,
                "row": payload,
            }
            job = create_job(kind="insert", payload=job_payload)

            def work() -> dict[str, Any]:
                result = _do_insert(engine, table, endpoint, payload)
                _invalidate_endpoint_cache(endpoint)
                return result

            enqueue_job(job.id, work)
            _audit(spec, "create.async", endpoint, request, status=202, resource_id=None, meta={"job_id": job.id})
            return _json_response(
                {"job_id": job.id, "status": "queued"},
                status_code=202,
                headers={"Location": f"/jobs/{job.id}"},
            )

        result = _do_insert(engine, table, endpoint, payload)
        _invalidate_endpoint_cache(endpoint)
        _idempotency_commit(
            store_key,
            method="POST",
            path=path,
            payload=payload,
            status_code=201,
            body=result,
            ttl_seconds=spec.app.idempotency.ttl_seconds,
        )
        _audit(spec, "create", endpoint, request, status=201, resource_id=result.get(endpoint.primary_key))
        dispatch_webhooks(spec, event="create", endpoint=endpoint.name, payload=result)
        headers = {"ETag": _etag_for(result, endpoint)}
        return _json_response(result, status_code=201, headers=headers)

    create_item.__name__ = f"create_{endpoint.name}"
    router.add_api_route(
        endpoint.path,
        create_item,
        methods=["POST"],
        status_code=201,
        tags=tags,
        name=f"create_{endpoint.name}",
    )


def _add_bulk(router, engine, table, endpoint, spec, write_model, tags) -> None:  # type: ignore[no-untyped-def]
    async def bulk_create(request: Request) -> Any:
        try:
            raw = await request.json()
        except Exception as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail="Request body must be JSON.",
            ) from exc
        if not isinstance(raw, dict) or "items" not in raw or not isinstance(raw["items"], list):
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail='Body must be {"items": [ ... ]}.',
            )
        if len(raw["items"]) > 100:
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail="Bulk max 100 items.",
            )

        created: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for idx, item in enumerate(raw["items"]):
            try:
                payload = write_model.model_validate(item).model_dump(exclude_unset=True)
                validate_payload(endpoint, payload)
                payload = _inject_row_level(endpoint, request, payload)
                created.append(_do_insert(engine, table, endpoint, payload))
            except AppError as exc:
                errors.append({"index": idx, "status": exc.status, "detail": exc.detail})
            except Exception as exc:  # noqa: BLE001
                errors.append({"index": idx, "status": 500, "detail": str(exc)})

        if created:
            _invalidate_endpoint_cache(endpoint)
        _audit(
            spec,
            "bulk_create",
            endpoint,
            request,
            status=207 if errors else 201,
            meta={"created": len(created), "errors": len(errors)},
        )
        status = 201 if not errors else (207 if created else 422)
        return _json_response({"items": created, "errors": errors}, status_code=status)

    bulk_create.__name__ = f"bulk_create_{endpoint.name}"
    router.add_api_route(
        f"{endpoint.path}/bulk",
        bulk_create,
        methods=["POST"],
        tags=tags,
        name=f"bulk_create_{endpoint.name}",
    )


def _add_update(router, engine, table, endpoint, spec, item_model, write_model, tags) -> None:  # type: ignore[no-untyped-def]
    pk = endpoint.primary_key
    pk_type = _python_type(table.c[pk].type)

    async def update_item(request: Request, item_id: Any) -> Any:
        payload = await _read_write_body(request, write_model)
        if not payload:
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail="Request body must include at least one field.",
            )
        validate_payload(endpoint, payload)
        # Prevent changing ownership column away from claim
        if endpoint.row_level and endpoint.row_level.column in payload:
            payload = _inject_row_level(endpoint, request, payload)

        path = f"{endpoint.path}/{item_id}"
        store_key = _idempotency_begin(
            request, spec=spec, endpoint=endpoint, method="PATCH", path=path, payload=payload
        )
        if store_key:
            replay = _idempotency_replay_or_conflict(store_key, method="PATCH", path=path, payload=payload)
            if replay is not None:
                return replay

        current = _fetch_row(engine, table, endpoint, request, item_id)
        if current is None:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        _check_if_match(request, _etag_for(current, endpoint))

        clauses = apply_security_clauses([table.c[pk] == item_id], table, endpoint, request)
        stmt = (
            table.update()
            .where(combine(clauses))
            .values(**payload)
            .returning(*(table.c[f] for f in endpoint.fields))
        )
        try:
            with engine.begin() as conn:
                row = conn.execute(stmt).fetchone()
        except IntegrityError as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/conflict",
                title="Conflict",
                status=409,
                detail="Update violated a database constraint.",
            ) from exc
        except SQLAlchemyError as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/database-error",
                title="Database error",
                status=500,
                detail=exc.__class__.__name__,
            ) from exc
        if row is None:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        result = _row_to_dict(row, endpoint.fields)
        _invalidate_endpoint_cache(endpoint)
        _idempotency_commit(
            store_key,
            method="PATCH",
            path=path,
            payload=payload,
            status_code=200,
            body=result,
            ttl_seconds=spec.app.idempotency.ttl_seconds,
        )
        _audit(spec, "update", endpoint, request, status=200, resource_id=item_id)
        dispatch_webhooks(spec, event="update", endpoint=endpoint.name, payload=result)
        return _json_response(result, headers={"ETag": _etag_for(result, endpoint)})

    methods = []
    if HttpMethod.PUT in endpoint.methods:
        methods.append("PUT")
    if HttpMethod.PATCH in endpoint.methods:
        methods.append("PATCH")
    update_item.__name__ = f"update_{endpoint.name}"
    _bind_path_type(update_item, "item_id", pk_type)
    router.add_api_route(
        f"{endpoint.path}/{{item_id}}",
        update_item,
        methods=methods,
        tags=tags,
        name=f"update_{endpoint.name}",
    )


def _add_delete(router, engine, table, endpoint, spec, tags) -> None:  # type: ignore[no-untyped-def]
    pk = endpoint.primary_key
    pk_type = _python_type(table.c[pk].type)

    async def delete_item(request: Request, item_id: Any) -> Response:
        path = f"{endpoint.path}/{item_id}"
        payload = {"id": item_id}
        store_key = _idempotency_begin(
            request, spec=spec, endpoint=endpoint, method="DELETE", path=path, payload=payload
        )
        if store_key:
            replay = _idempotency_replay_or_conflict(store_key, method="DELETE", path=path, payload=payload)
            if replay is not None:
                return replay

        current = _fetch_row(engine, table, endpoint, request, item_id)
        if current is None:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        _check_if_match(request, _etag_for(current, endpoint))

        clauses = apply_security_clauses([table.c[pk] == item_id], table, endpoint, request)
        where = combine(clauses)
        try:
            with engine.begin() as conn:
                if endpoint.soft_delete and endpoint.soft_delete.column in table.c:
                    stmt = (
                        table.update()
                        .where(where)
                        .values({endpoint.soft_delete.column: datetime.now(UTC)})
                    )
                    result = conn.execute(stmt)
                else:
                    result = conn.execute(table.delete().where(where))
        except SQLAlchemyError as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/database-error",
                title="Database error",
                status=500,
                detail=exc.__class__.__name__,
            ) from exc
        if result.rowcount == 0:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        _invalidate_endpoint_cache(endpoint)
        _idempotency_commit(
            store_key,
            method="DELETE",
            path=path,
            payload=payload,
            status_code=204,
            body=None,
            ttl_seconds=spec.app.idempotency.ttl_seconds,
        )
        _audit(spec, "delete", endpoint, request, status=204, resource_id=item_id)
        dispatch_webhooks(
            spec,
            event="delete",
            endpoint=endpoint.name,
            payload={"id": item_id},
        )
        return Response(status_code=204)

    delete_item.__name__ = f"delete_{endpoint.name}"
    _bind_path_type(delete_item, "item_id", pk_type)
    router.add_api_route(
        f"{endpoint.path}/{{item_id}}",
        delete_item,
        methods=["DELETE"],
        response_class=Response,
        status_code=204,
        tags=tags,
        name=f"delete_{endpoint.name}",
    )
