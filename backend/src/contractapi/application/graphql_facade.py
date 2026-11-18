"""GraphQL facade generated from ApiSpec (optional: strawberry)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, and_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.application.validation_rules import validate_payload
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, EndpointSpec, HttpMethod
from contractapi.infrastructure.security.auth import enforce_endpoint_roles

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

try:
    import asyncio
    from collections.abc import AsyncGenerator

    import strawberry
    from strawberry.fastapi import GraphQLRouter
    from strawberry.scalars import JSON
    from strawberry.types import Info

    def _resolve_endpoint_rows(
        info: Info,
        name: str,
        limit: int,
        params: JSON | None,
        include_relations: bool,
        roles: list[str] | None,
    ) -> list[dict[str, Any]]:
        endpoints: dict[str, EndpointSpec] = info.context["endpoints"]
        engine: Engine = info.context["engine"]
        spec: ApiSpec = info.context["spec"]
        principal: dict[str, Any] = info.context["principal"]
        ep = endpoints.get(name)
        if ep is None:
            raise ValueError(
                f"Unknown or non-GraphQL endpoint '{name}'. "
                f"Allowed: {sorted(endpoints)}"
            )
        enforce_endpoint_roles(principal, ep.roles)
        bind = params if isinstance(params, dict) else {}
        rows = _fetch_rows(
            engine,
            ep,
            limit,
            bind_params=bind,
            principal=principal,
        )
        if include_relations and (not ep.is_sql) and ep.relations:
            from contractapi.application.relations import load_relations

            load_relations(engine, MetaData(), ep.relations, rows)
        return _apply_rbac(spec, ep, rows, _effective_roles(principal, roles))

    @strawberry.type
    class Query:
        @strawberry.field
        async def endpoint(
            self,
            info: Info,
            name: str,
            limit: int = 20,
            params: JSON | None = None,
            include_relations: bool = True,
            roles: list[str] | None = None,
        ) -> list[JSON]:
            """`roles` can only narrow to a subset of the caller's token roles."""
            # Blocking DB work runs in a thread so it never stalls the event loop.
            return await asyncio.to_thread(
                _resolve_endpoint_rows, info, name, limit, params, include_relations, roles or None
            )

        @strawberry.field
        def available_endpoints(self, info: Info) -> list[str]:
            return sorted(info.context["endpoints"])

        @strawberry.field
        def available_mutations(self, info: Info) -> list[str]:
            return sorted(info.context.get("mutation_ops") or [])

    @strawberry.type
    class Mutation:
        @strawberry.field
        async def create_item(self, info: Info, endpoint: str, data: JSON) -> JSON:
            payload = data if isinstance(data, dict) else {}
            return await asyncio.to_thread(_mutate_create, info, endpoint, payload)

        @strawberry.field
        async def update_item(self, info: Info, endpoint: str, id: JSON, data: JSON) -> JSON:
            payload = data if isinstance(data, dict) else {}
            return await asyncio.to_thread(_mutate_update, info, endpoint, id, payload)

        @strawberry.field
        async def delete_item(self, info: Info, endpoint: str, id: JSON) -> JSON:
            return await asyncio.to_thread(_mutate_delete, info, endpoint, id)

    @strawberry.type
    class Subscription:
        @strawberry.subscription
        async def endpoint_stream(
            self,
            info: Info,
            name: str,
            limit: int = 20,
            interval_seconds: float = 2.0,
            include_relations: bool = False,
            roles: list[str] | None = None,
        ) -> AsyncGenerator[list[JSON], None]:
            """Poll-based subscription MVP (WebSocket)."""
            delay = max(0.5, min(float(interval_seconds), 30.0))
            while True:
                yield await asyncio.to_thread(
                    _resolve_endpoint_rows, info, name, limit, None, include_relations, roles or None
                )
                await asyncio.sleep(delay)

    _GRAPHQL_SCHEMA = strawberry.Schema(
        query=Query, mutation=Mutation, subscription=Subscription
    )
    _GRAPHQL_READY = True
except ImportError:  # pragma: no cover - optional extra
    GraphQLRouter = None  # type: ignore[misc, assignment]
    _GRAPHQL_SCHEMA = None
    _GRAPHQL_READY = False


def graphql_available() -> bool:
    return _GRAPHQL_READY


def _quote_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Unsafe identifier: {name}")
    return f'"{name}"'


def _load_table(engine: Engine, ep: EndpointSpec) -> Table:
    """Reflect table when possible; otherwise build a lightweight column map."""
    metadata = MetaData()
    schema = ep.schema_name or None
    if schema in {"main", "public"}:
        try:
            return Table(ep.table, metadata, autoload_with=engine)
        except SQLAlchemyError:
            metadata = MetaData()  # retry with an explicit schema below
    try:
        return Table(ep.table, metadata, schema=schema, autoload_with=engine)
    except SQLAlchemyError:
        cols = [Column(name, String) for name in ep.fields]
        return Table(ep.table, metadata, *cols, schema=schema)


def _fetch_sql_rows(
    engine: Engine,
    ep: EndpointSpec,
    limit: int,
    *,
    bind_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    inner = (ep.sql or "").strip().rstrip(";").strip()
    if not inner:
        raise ValueError(f"Endpoint '{ep.name}' has empty SQL.")
    fields_sql = ", ".join(f"q.{_quote_ident(f)}" for f in ep.fields)
    sql = text(f"SELECT {fields_sql} FROM ({inner}) AS q LIMIT :_limit")
    params: dict[str, Any] = {"_limit": limit}
    # Apply declared sql_params defaults / provided binds only.
    provided = bind_params or {}
    for p in ep.sql_params:
        if p.name in provided:
            params[p.name] = provided[p.name]
        elif p.required and p.default is None:
            raise ValueError(f"Missing required SQL param '{p.name}'.")
        elif p.default is not None:
            params[p.name] = p.default
    from contractapi.application.sql_endpoint import begin_read_only

    with engine.connect() as conn:
        begin_read_only(conn)
        rows = conn.execute(sql, params).mappings().all()
    return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]


def _claim_value(principal: dict[str, Any], claim: str) -> Any:
    """Same lookup as REST row-level: verified token claims first, then principal fields."""
    value = (principal.get("claims") or {}).get(claim)
    return principal.get(claim) if value is None else value


def _effective_roles(principal: dict[str, Any], requested: list[str] | None) -> list[str]:
    """Token roles, optionally narrowed by the client — never widened."""
    own = [str(r) for r in (principal.get("roles") or [])]
    if not requested:
        return own
    return [r for r in own if r in set(requested)]


def _row_level_missing(ep: EndpointSpec) -> AppError:
    return AppError(
        type_="https://contractapi.dev/problems/forbidden",
        title="Forbidden",
        status=403,
        detail=f"Missing claim '{ep.row_level.claim}' for row-level access on '{ep.name}'.",
    )


def _security_sql(
    ep: EndpointSpec, principal: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """Soft-delete + row-level clauses for GraphQL table reads (REST parity)."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if ep.soft_delete and ep.soft_delete.column:
        clauses.append(f"{_quote_ident(ep.soft_delete.column)} IS NULL")
    if ep.row_level and ep.row_level.column:
        value = _claim_value(principal, ep.row_level.claim)
        if value is None and ep.row_level.required:
            raise _row_level_missing(ep)
        if value is not None:
            clauses.append(f"{_quote_ident(ep.row_level.column)} = :_rl_claim")
            params["_rl_claim"] = value
    return clauses, params


def _fetch_rows(
    engine: Engine,
    ep: EndpointSpec,
    limit: int,
    *,
    bind_params: dict[str, Any] | None = None,
    principal: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, ep.pagination.max_limit))
    if ep.is_sql:
        return _fetch_sql_rows(engine, ep, limit, bind_params=bind_params)
    sec_clauses, sec_params = _security_sql(ep, principal or {})
    fields_sql = ", ".join(_quote_ident(f) for f in ep.fields)
    schema = ep.schema_name
    if schema and schema not in {"main", ""}:
        table_sql = f"{_quote_ident(schema)}.{_quote_ident(ep.table)}"
    else:
        table_sql = _quote_ident(ep.table)
    where = f" WHERE {' AND '.join(sec_clauses)}" if sec_clauses else ""
    sql = text(f"SELECT {fields_sql} FROM {table_sql}{where} LIMIT :limit")
    params = {"limit": limit, **sec_params}
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]


def _apply_rbac(
    spec: ApiSpec,
    ep: EndpointSpec,
    rows: list[dict[str, Any]],
    roles: list[str],
) -> list[dict[str, Any]]:
    """Match REST `_visible_fields` when app.rbac is configured."""
    allowed = spec.rbac_fields_for(ep.name, roles)
    if allowed is None:
        return rows
    keep = set(allowed) | {ep.primary_key} | {r.name for r in ep.relations}
    return [{k: v for k, v in row.items() if k in keep} for row in rows]


def _writable_keys(ep: EndpointSpec) -> set[str]:
    if ep.writable_fields:
        return set(ep.writable_fields)
    return {f for f in ep.fields if f != ep.primary_key}


def _filter_write_payload(ep: EndpointSpec, data: dict[str, Any]) -> dict[str, Any]:
    allowed = _writable_keys(ep)
    out = {k: v for k, v in data.items() if k in allowed}
    if not out and data:
        raise ValueError(
            f"No writable fields in payload for '{ep.name}'. Allowed: {sorted(allowed)}"
        )
    return out


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
    stmt = table.insert().values(**payload)
    returning = [table.c[f] for f in ep.fields if f in table.c]
    result: dict[str, Any] | None = None
    try:
        with engine.begin() as conn:
            if returning:
                row = conn.execute(stmt.returning(*returning)).mappings().first()
                if row is not None:
                    result = {k: _jsonable(v) for k, v in dict(row).items()}
            if result is None:
                conn.execute(stmt)
                # Fallback fetch by PK when RETURNING unsupported
                pk = ep.primary_key
                if pk in payload:
                    cols = [table.c[f] for f in ep.fields if f in table.c]
                    row = (
                        conn.execute(select(*cols).where(table.c[pk] == payload[pk]))
                        .mappings()
                        .first()
                    )
                    if row:
                        result = {k: _jsonable(v) for k, v in dict(row).items()}
                if result is None:
                    result = {k: _jsonable(v) for k, v in payload.items()}
    except IntegrityError as exc:
        raise ValueError("Insert violated a database constraint.") from exc
    except SQLAlchemyError as exc:
        raise ValueError(f"Database error: {exc.__class__.__name__}") from exc
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
    returning = [table.c[f] for f in ep.fields if f in table.c]
    result: dict[str, Any] | None = None
    try:
        with engine.begin() as conn:
            stmt = table.update().where(where).values(**payload)
            if returning:
                row = conn.execute(stmt.returning(*returning)).mappings().first()
                if row is None:
                    raise ValueError(f"{name} with {pk}={item_id} not found")
                result = {k: _jsonable(v) for k, v in dict(row).items()}
            else:
                if conn.execute(stmt).rowcount == 0:
                    raise ValueError(f"{name} with {pk}={item_id} not found")
                cols = [table.c[f] for f in ep.fields if f in table.c]
                row = conn.execute(select(*cols).where(where)).mappings().first()
                if not row:
                    raise ValueError(f"{name} with {pk}={item_id} not found")
                result = {k: _jsonable(v) for k, v in dict(row).items()}
    except IntegrityError as exc:
        raise ValueError("Update violated a database constraint.") from exc
    except SQLAlchemyError as exc:
        raise ValueError(f"Database error: {exc.__class__.__name__}") from exc
    _after_write(spec, ep, principal, "update", result, item_id)
    return _visible(spec, ep, principal, result)


def _mutate_delete(info: Any, name: str, item_id: Any) -> dict[str, Any]:
    ep, engine, spec, principal = _write_target(info, name, {HttpMethod.DELETE}, "Delete")
    table = _load_table(engine, ep)
    pk = ep.primary_key
    if pk not in table.c:
        raise ValueError(f"Primary key '{pk}' missing on table.")
    where = and_(table.c[pk] == item_id, *_row_filters(ep, table, principal))
    with engine.begin() as conn:
        if ep.soft_delete and ep.soft_delete.column in table.c:
            from datetime import datetime, timezone

            result = conn.execute(
                table.update()
                .where(where)
                .values({ep.soft_delete.column: datetime.now(timezone.utc)})
            )
        else:
            result = conn.execute(table.delete().where(where))
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


def mount_graphql(app: Any, engine: Engine, spec: ApiSpec) -> None:
    """
    Mount /graphql for contract-scoped reads (table + SQL) and table mutations.

    GA when strawberry is installed: pip install 'contractapi[graphql]'.
    Authorization comes only from the verified principal (never from GraphQL args).
    """
    if not graphql_available() or GraphQLRouter is None or _GRAPHQL_SCHEMA is None:
        return

    from fastapi.requests import HTTPConnection

    from contractapi.infrastructure.security.auth import authenticate_request

    endpoints = {
        e.name: e for e in spec.endpoints if HttpMethod.GET in e.methods
    }
    write_endpoints = {
        e.name: e
        for e in spec.endpoints
        if not e.is_sql
        and (
            HttpMethod.POST in e.methods
            or HttpMethod.PATCH in e.methods
            or HttpMethod.PUT in e.methods
            or HttpMethod.DELETE in e.methods
        )
    }
    if not endpoints and not write_endpoints:
        return

    mutation_ops = _mutation_ops(write_endpoints)

    def context_getter(conn: HTTPConnection) -> dict[str, Any]:
        # HTTP requests were authenticated by the data-plane middleware;
        # WebSocket subscriptions bypass it, so authenticate here (fail closed).
        principal = getattr(conn.state, "principal", None)
        if principal is None:
            principal = authenticate_request(conn, spec)  # type: ignore[arg-type]
        return {
            "engine": engine,
            "endpoints": endpoints,
            "write_endpoints": write_endpoints,
            "mutation_ops": mutation_ops,
            "spec": spec,
            "principal": principal,
        }

    # Postponed annotations: bind the real class so FastAPI injects the connection.
    context_getter.__annotations__["conn"] = HTTPConnection
    app.include_router(
        GraphQLRouter(_GRAPHQL_SCHEMA, context_getter=context_getter),
        prefix="/graphql",
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def graphql_status(spec: ApiSpec) -> dict[str, Any]:
    reads = [e.name for e in spec.endpoints if HttpMethod.GET in e.methods]
    writes = {
        e.name: e
        for e in spec.endpoints
        if not e.is_sql
        and (
            HttpMethod.POST in e.methods
            or HttpMethod.PATCH in e.methods
            or HttpMethod.PUT in e.methods
            or HttpMethod.DELETE in e.methods
        )
    }
    return {
        "available": graphql_available(),
        "install": "pip install 'contractapi[graphql]'",
        "endpoints": reads,
        "mutations": _mutation_ops(writes),
    }
