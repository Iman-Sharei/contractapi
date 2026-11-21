"""GraphQL create/update/delete with REST parity: roles, row-level, validations, audit, webhooks, cache."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Table, and_
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.application.data_api.write_rules import (
    db_timezone,
    for_create,
    for_update,
    now_for,
)
from contractapi.application.data_api.write_support import IN_USE_DETAIL, conflict_error
from contractapi.application.graphql_ops import (
    _apply_rbac,
    _claim_value,
    _effective_roles,
    _jsonable,
    _load_table,
    _row_level_missing,
)
from contractapi.application.validation_rules import validate_payload
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, EndpointSpec, HttpMethod
from contractapi.infrastructure.db.dialects import insert_returning, update_returning
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.security.auth import enforce_endpoint_roles


def _writable_keys(ep: EndpointSpec) -> set[str]:
    if ep.writable_fields:
        return set(ep.writable_fields)
    return {f for f in ep.fields if f != ep.primary_key}


def _filter_write_payload(ep: EndpointSpec, data: dict[str, Any]) -> dict[str, Any]:
    allowed = _writable_keys(ep)
    refused = sorted(set(data) - allowed)
    if refused:  # same as REST (422): never silently drop what the caller sent
        raise ValueError(
            f"These fields cannot be written on '{ep.name}': {', '.join(refused)}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    return dict(data)


def _write_target(
    info: Any, name: str, methods: set[HttpMethod], verb: str
) -> tuple[EndpointSpec, Engine, ApiSpec, dict[str, Any]]:
    ep = info.context["write_endpoints"].get(name)
    if ep is None or not (methods & set(ep.methods)):
        raise ValueError(f"{verb} not allowed for endpoint '{name}'.")
    if ep.is_sql:
        raise ValueError("SQL endpoints are read-only over GraphQL.")
    principal: dict[str, Any] = info.context["principal"]
    enforce_endpoint_roles(principal, ep.roles)
    return ep, info.context["engine"], info.context["spec"], principal


def _force_row_level(
    ep: EndpointSpec, principal: dict[str, Any], payload: dict[str, Any], *, always: bool
) -> dict[str, Any]:
    """Owner column always equals the caller's claim (REST `_inject_row_level` parity)."""
    cfg = ep.row_level
    if not cfg or (not always and cfg.column not in payload):
        return payload
    value = _claim_value(principal, cfg.claim)
    if value is None:
        if cfg.required:
            raise _row_level_missing(ep)
        return payload
    if cfg.column in payload and payload[cfg.column] != value:
        raise AppError(
            type_="https://contractapi.dev/problems/forbidden",
            title="Forbidden",
            status=403,
            detail=f"Cannot set '{cfg.column}' to a value other than your claim.",
        )
    return {**payload, cfg.column: value}


def _row_filters(ep: EndpointSpec, table: Table, principal: dict[str, Any]) -> list[Any]:
    """WHERE clauses that scope update/delete to rows the caller may see."""
    out: list[Any] = []
    if ep.soft_delete and ep.soft_delete.column in table.c:
        out.append(table.c[ep.soft_delete.column].is_(None))
    if ep.row_level:
        value = _claim_value(principal, ep.row_level.claim)
        if value is None:
            if ep.row_level.required:
                raise _row_level_missing(ep)
        else:
            out.append(table.c[ep.row_level.column] == value)
    return out


def _after_write(
    spec: ApiSpec,
    ep: EndpointSpec,
    principal: dict[str, Any],
    event: str,
    payload: dict[str, Any],
    resource_id: Any,
) -> None:
    """Same side effects as REST writes: cache invalidation, audit, webhooks."""
    from contractapi.application.data_api_builder import _invalidate_endpoint_cache
    from contractapi.infrastructure.audit import audit_event
    from contractapi.infrastructure.webhooks import dispatch_webhooks

    _invalidate_endpoint_cache(spec, ep)
    if spec.app.audit_enabled:
        audit_event(
            action=f"graphql.{event}",
            endpoint=ep.name,
            resource_id=resource_id,
            principal=principal,
            status=200,
        )
    dispatch_webhooks(spec, event=event, endpoint=ep.name, payload=payload)


def _visible(spec: ApiSpec, ep: EndpointSpec, principal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return _apply_rbac(spec, ep, [row], _effective_roles(principal, None))[0]


def _mutate_create(info: Any, name: str, data: dict[str, Any]) -> dict[str, Any]:
    ep, engine, spec, principal = _write_target(info, name, {HttpMethod.POST}, "Create")
    payload = _force_row_level(ep, principal, _filter_write_payload(ep, data), always=True)
    validate_payload(ep, payload)
    table = _load_table(engine, ep)
    payload = for_create(ep, table, payload, db_timezone(spec))  # same write rules as REST
    result: dict[str, Any] | None = None
    try:
        with engine.begin() as conn:
            fields = [f for f in ep.fields if f in table.c]
            row = insert_returning(conn, table, payload, fields, ep.primary_key)
            result = {k: _jsonable(v) for k, v in dict(row or payload).items()}
    except IntegrityError as exc:
        raise ValueError(conflict_error(exc).detail) from exc
    except SQLAlchemyError as exc:
        raise ValueError(db_error(exc).detail) from exc
    _after_write(spec, ep, principal, "create", result, result.get(ep.primary_key))
    return _visible(spec, ep, principal, result)


def _mutate_update(info: Any, name: str, item_id: Any, data: dict[str, Any]) -> dict[str, Any]:
    ep, engine, spec, principal = _write_target(
        info, name, {HttpMethod.PATCH, HttpMethod.PUT}, "Update"
    )
    payload = _force_row_level(ep, principal, _filter_write_payload(ep, data), always=False)
    if not payload:
        raise ValueError("Update payload must include at least one writable field.")
    validate_payload(ep, payload)
    table = _load_table(engine, ep)
    pk = ep.primary_key
    if pk not in table.c:
        raise ValueError(f"Primary key '{pk}' missing on table.")
    where = and_(table.c[pk] == item_id, *_row_filters(ep, table, principal))
    payload = for_update(ep, table, payload, db_timezone(spec))
    result: dict[str, Any] | None = None
    try:
        with engine.begin() as conn:
            fields = [f for f in ep.fields if f in table.c]
            row = update_returning(conn, table, where, payload, fields)
            if row is None:
                raise ValueError(f"{name} with {pk}={item_id} not found")
            result = {k: _jsonable(v) for k, v in dict(row).items()}
    except IntegrityError as exc:
        raise ValueError(conflict_error(exc).detail) from exc
    except SQLAlchemyError as exc:
        raise ValueError(db_error(exc).detail) from exc
    _after_write(spec, ep, principal, "update", result, item_id)
    return _visible(spec, ep, principal, result)


def _mutate_delete(info: Any, name: str, item_id: Any) -> dict[str, Any]:
    ep, engine, spec, principal = _write_target(info, name, {HttpMethod.DELETE}, "Delete")
    table = _load_table(engine, ep)
    pk = ep.primary_key
    if pk not in table.c:
        raise ValueError(f"Primary key '{pk}' missing on table.")
    where = and_(table.c[pk] == item_id, *_row_filters(ep, table, principal))
    try:
        with engine.begin() as conn:
            if ep.soft_delete and ep.soft_delete.column in table.c:
                col = ep.soft_delete.column
                result = conn.execute(
                    table.update().where(where).values({col: now_for(table, col, db_timezone(spec))})
                )
            else:
                result = conn.execute(table.delete().where(where))
    except IntegrityError as exc:
        raise ValueError(IN_USE_DETAIL) from exc
    except SQLAlchemyError as exc:
        raise ValueError(db_error(exc).detail) from exc
    if result.rowcount == 0:
        raise ValueError(f"{name} with {pk}={item_id} not found")
    _after_write(spec, ep, principal, "delete", {"id": _jsonable(item_id)}, item_id)
    return {"deleted": True, "id": _jsonable(item_id), "endpoint": name}


def _mutation_ops(write_endpoints: dict[str, EndpointSpec]) -> list[str]:
    ops: list[str] = []
    for name, ep in write_endpoints.items():
        if HttpMethod.POST in ep.methods:
            ops.append(f"create:{name}")
        if {HttpMethod.PATCH, HttpMethod.PUT} & set(ep.methods):
            ops.append(f"update:{name}")
        if HttpMethod.DELETE in ep.methods:
            ops.append(f"delete:{name}")
    return ops
