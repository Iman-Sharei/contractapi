"""Shared helpers for generated data-plane endpoints (serialization, RBAC fields, ETags, audit, cache)."""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, time, tzinfo
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import Table, select
from sqlalchemy.engine import Engine

from contractapi.application.query_filters import combine
from contractapi.application.row_security import apply_security_clauses
from contractapi.core.errors import (
    AppError,
)
from contractapi.core.logging import get_logger
from contractapi.domain.models.spec import (
    ApiSpec,
    EndpointSpec,
    PaginationMode,
)
from contractapi.infrastructure.audit import audit_event
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.security.auth import (
    enforce_endpoint_roles,
)

logger = get_logger("contractapi.data")


def _python_type(sa_type: Any) -> Any:
    """Python type of a column for request/response models.

    Uses SQLAlchemy's own mapping, so dialect types are right: MySQL DATETIME / SQL Server
    DATETIME2 → datetime (not date), TINYINT → int, BIT → bool. Exact decimals are typed by
    write_models when the API returns them as text."""
    try:
        py = sa_type.python_type
    except (NotImplementedError, AttributeError):
        py = object
    if py is Decimal:
        return float
    if py in (bool, int, float, str, date, datetime, time, list):
        return py
    name = type(sa_type).__name__.upper()
    if py is dict or "JSON" in name:
        return Any  # JSON columns hold objects, arrays or scalars
    if "MONEY" in name:
        return float
    if name == "YEAR":
        return int
    return str  # UUID, intervals, network addresses, … travel as text in JSON


@dataclass(frozen=True)
class OutputFormat:
    """How values are written to JSON for one API (spec `app.decimals`, `database.timezone`)."""

    decimals: str = "number"
    tz: tzinfo | None = None


# Set per request by OutputFormatMiddleware. ponytail: async-job results built on a worker
# thread use the default format; pass the format explicitly if that ever matters.
OUTPUT_FORMAT: ContextVar[OutputFormat] = ContextVar("contractapi_output", default=OutputFormat())  # noqa: B039 — frozen


def output_format_for(spec: ApiSpec) -> OutputFormat:
    from zoneinfo import ZoneInfo

    tz = spec.database.timezone
    return OutputFormat(decimals=spec.app.decimals, tz=ZoneInfo(tz) if tz else None)


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        if OUTPUT_FORMAT.get().decimals == "string":
            return format(value, "f")  # exact digits, never "1E+2"
        return float(value)
    if isinstance(value, datetime):
        tz = OUTPUT_FORMAT.get().tz
        if tz is not None and value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.isoformat()
    if isinstance(value, date):
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


def _select_relations(endpoint: EndpointSpec, include: str | None):
    """Pick relations to embed. omit/None/* → all; empty → none; else comma names."""
    if not endpoint.relations:
        return []
    if include is None:
        return list(endpoint.relations)
    raw = include.strip()
    if raw in {"", "0", "false", "none"}:
        return []
    if raw == "*":
        return list(endpoint.relations)
    wanted = {p.strip() for p in raw.split(",") if p.strip()}
    selected = [r for r in endpoint.relations if r.name in wanted]
    unknown = sorted(wanted - {r.name for r in endpoint.relations})
    if unknown:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-include",
            title="Unknown relation",
            status=400,
            detail="One or more include/expand names are not configured on this endpoint.",
            extensions={
                "allowed": [r.name for r in endpoint.relations],
                "rejected": unknown,
            },
        )
    return selected


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


def _model_name(name: str) -> str:
    return "".join(part.title() for part in name.split("_"))


def _cache_prefix(spec: ApiSpec, endpoint: EndpointSpec) -> str:
    # Namespaced per contract so two active APIs never share entries.
    return f"ep:{spec.namespace}:{endpoint.name}:"


def _row_scope(endpoint: EndpointSpec, request: Request) -> str:
    """Cache/idempotency scope for row-level endpoints: the caller's claim value."""
    cfg = endpoint.row_level
    if not cfg:
        return ""
    principal = getattr(request.state, "principal", {}) or {}
    value = (principal.get("claims") or {}).get(cfg.claim)
    if value is None:
        value = principal.get(cfg.claim)
    return f"rl={json.dumps(value, default=str)}:"


def _invalidate_endpoint_cache(spec: ApiSpec, endpoint: EndpointSpec) -> None:
    response_cache.invalidate_prefix(_cache_prefix(spec, endpoint))


def _rbac_fields(spec: ApiSpec, endpoint: EndpointSpec, request: Request) -> list[str]:
    """Endpoint role gate + the fields this caller's roles may see (reads, writes, filters)."""
    principal = getattr(request.state, "principal", {"roles": []})
    enforce_endpoint_roles(principal, endpoint.roles)
    rbac = spec.rbac_fields_for(endpoint.name, list(principal.get("roles") or []))
    if rbac is None:
        return list(endpoint.fields)
    fields = [f for f in endpoint.fields if f in rbac or f == endpoint.primary_key]
    if endpoint.primary_key in endpoint.fields and endpoint.primary_key not in fields:
        fields = [endpoint.primary_key, *fields]
    return fields


def _visible_fields(spec: ApiSpec, endpoint: EndpointSpec, request: Request) -> list[str]:
    fields = _rbac_fields(spec, endpoint, request)

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


def _mounted_url(request: Request):  # type: ignore[no-untyped-def]
    """Request URL including its mount (/data, /apis/<name>): links must work for clients."""
    root = request.scope.get("root_path") or ""
    url = request.url
    if root and not url.path.startswith(root):
        url = url.replace(path=root + url.path)
    return url


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
            next_url = str(_mounted_url(request).include_query_params(cursor=next_cursor, limit=limit))
            links.append(f'<{next_url}>; rel="next"')
    else:
        if total is not None and offset + limit < total:
            next_url = str(_mounted_url(request).include_query_params(offset=offset + limit, limit=limit))
            links.append(f'<{next_url}>; rel="next"')
        if offset > 0:
            prev = max(0, offset - limit)
            prev_url = str(_mounted_url(request).include_query_params(offset=prev, limit=limit))
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


def _audit(spec: ApiSpec, action: str, endpoint: EndpointSpec, request: Request, **kwargs: Any) -> None:
    if not spec.app.audit_enabled:
        return
    audit_event(
        action=action,
        api=getattr(request.app.state, "api_name", None),
        endpoint=endpoint.name,
        principal=getattr(request.state, "principal", None),
        **kwargs,
    )


