"""Write-path helpers: body validation, row-level injection, idempotency, inserts."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, ValidationError, create_model
from sqlalchemy import Table
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.application.data_api.common import (
    _model_name,
    _python_type,
    _row_to_dict,
)
from contractapi.core.errors import (
    AppError,
)
from contractapi.domain.models.spec import (
    ApiSpec,
    EndpointSpec,
)
from contractapi.infrastructure.db.dialects import insert_returning
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.idempotency import (
    IdempotentRecord,
    fingerprint_payload,
    idempotency_store,
    make_scope_key,
    serialize_json_body,
)


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
    principal = getattr(request.state, "principal", {}) or {}
    # Scope per API + caller so a reused key never replays someone else's response.
    scope = f"{spec.namespace}:{principal.get('sub') or 'anon'}:{endpoint.name}:{method}:{path}"
    return make_scope_key(scope, idem_key)


def _idempotency_replay_or_conflict(
    store_key: str,
    *,
    method: str,
    path: str,
    payload: dict[str, Any],
    request: Request,
) -> Response | None:
    body = serialize_json_body(payload)
    fp = fingerprint_payload(method, path, body)
    existing = idempotency_store.get(store_key)
    if existing is None:
        # First request with this key: reserve it atomically so a concurrent duplicate
        # gets 409 instead of performing the write twice. Released on commit or on error.
        if not idempotency_store.claim(store_key):
            raise AppError(
                type_="https://contractapi.dev/problems/idempotency-in-progress",
                title="Request in progress",
                status=409,
                detail="A request with this Idempotency-Key is still being processed. Retry shortly.",
            )
        request.state.idem_lock = store_key
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
    idempotency_store.release(store_key)


def _validate_write_body(raw: Any, write_model: type[BaseModel]) -> dict[str, Any]:
    if isinstance(raw, write_model):  # already validated by FastAPI from the declared body model
        return raw.model_dump(exclude_unset=True)
    if not isinstance(raw, dict):
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="Request body must be a JSON object.",
        )
    try:
        return write_model.model_validate(raw).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="One or more fields are invalid.",
            extensions={"errors": exc.errors(include_url=False, include_input=False)},
        ) from exc


def _bind_body(handler: Any, model: Any) -> None:
    """Postponed annotations: give FastAPI the real body model (documents it in OpenAPI)."""
    handler.__annotations__["body"] = model


CONFLICT_DETAIL = (
    "Another record already uses one of these values (for example the same email; a deleted "
    "record that is only hidden still counts), or a record it refers to does not exist."
)
IN_USE_DETAIL = (
    "Other records still refer to this one (for example the orders of a customer). Delete or "
    "move them first, or turn on soft delete for this endpoint."
)


def _created_location(endpoint: EndpointSpec, item_id: Any) -> str:
    # Relative reference (RFC 9110 §10.2.2): resolves against the collection URL under any mount.
    return f"{endpoint.path.rsplit('/', 1)[-1]}/{item_id}"


def _do_insert(engine: Engine, table: Table, endpoint: EndpointSpec, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        with engine.begin() as conn:
            row = insert_returning(conn, table, payload, endpoint.fields, endpoint.primary_key)
    except IntegrityError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/conflict",
            title="Conflict",
            status=409,
            detail=CONFLICT_DETAIL,
        ) from exc
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return _row_to_dict(row, endpoint.fields)
