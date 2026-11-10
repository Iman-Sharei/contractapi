"""GraphQL facade generated from ApiSpec (optional: strawberry)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.domain.models.spec import ApiSpec, EndpointSpec, HttpMethod

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

try:
    import strawberry
    from strawberry.fastapi import GraphQLRouter
    from strawberry.scalars import JSON
    from strawberry.types import Info

    @strawberry.type
    class Query:
        @strawberry.field
        def endpoint(
            self,
            info: Info,
            name: str,
            limit: int = 20,
            params: JSON | None = None,
            include_relations: bool = True,
            roles: list[str] | None = None,
        ) -> list[JSON]:
            endpoints: dict[str, EndpointSpec] = info.context["endpoints"]
            engine: Engine = info.context["engine"]
            spec: ApiSpec = info.context["spec"]
            ep = endpoints.get(name)
            if ep is None:
                raise ValueError(
                    f"Unknown or non-GraphQL endpoint '{name}'. "
                    f"Allowed: {sorted(endpoints)}"
                )
            bind = params if isinstance(params, dict) else {}
            rows = _fetch_rows(engine, ep, limit, bind_params=bind)
            if include_relations and (not ep.is_sql) and ep.relations:
                from contractapi.application.relations import load_relations

                load_relations(engine, MetaData(), ep.relations, rows)
            return _apply_rbac(spec, ep, rows, roles or [])

        @strawberry.field
        def available_endpoints(self, info: Info) -> list[str]:
            return sorted(info.context["endpoints"])

        @strawberry.field
        def available_mutations(self, info: Info) -> list[str]:
            return sorted(info.context.get("mutation_ops") or [])

    @strawberry.type
    class Mutation:
        @strawberry.field
        def create_item(self, info: Info, endpoint: str, data: JSON) -> JSON:
            return _mutate_create(info, endpoint, data if isinstance(data, dict) else {})

        @strawberry.field
        def update_item(self, info: Info, endpoint: str, id: JSON, data: JSON) -> JSON:
            return _mutate_update(
                info,
                endpoint,
                id,
                data if isinstance(data, dict) else {},
            )

        @strawberry.field
        def delete_item(self, info: Info, endpoint: str, id: JSON) -> JSON:
            return _mutate_delete(info, endpoint, id)

    _GRAPHQL_SCHEMA = strawberry.Schema(query=Query, mutation=Mutation)
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
        except Exception:
            pass
    try:
        return Table(ep.table, metadata, schema=schema, autoload_with=engine)
    except Exception:
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
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]


def _fetch_rows(
    engine: Engine,
    ep: EndpointSpec,
    limit: int,
    *,
    bind_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, ep.pagination.max_limit))
    if ep.is_sql:
        return _fetch_sql_rows(engine, ep, limit, bind_params=bind_params)
    try:
        table = _load_table(engine, ep)
        cols = [table.c[c] for c in ep.fields if c in table.c]
        if not cols:
            raise RuntimeError("no columns")
        with engine.connect() as conn:
            rows = conn.execute(select(*cols).limit(limit)).mappings().all()
        return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]
    except Exception:
        fields_sql = ", ".join(_quote_ident(f) for f in ep.fields)
        schema = ep.schema_name
        if schema and schema not in {"main", ""}:
            table_sql = f"{_quote_ident(schema)}.{_quote_ident(ep.table)}"
        else:
            table_sql = _quote_ident(ep.table)
        sql = text(f"SELECT {fields_sql} FROM {table_sql} LIMIT :limit")
        with engine.connect() as conn:
            rows = conn.execute(sql, {"limit": limit}).mappings().all()
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


def _write_endpoints(info: Any) -> dict[str, EndpointSpec]:
    return info.context["write_endpoints"]


def _mutate_create(info: Any, name: str, data: dict[str, Any]) -> dict[str, Any]:
    ep = _write_endpoints(info).get(name)
    if ep is None or HttpMethod.POST not in ep.methods:
        raise ValueError(f"Create not allowed for endpoint '{name}'.")
    if ep.is_sql:
        raise ValueError("SQL endpoints are read-only over GraphQL.")
    engine: Engine = info.context["engine"]
    payload = _filter_write_payload(ep, data)
    table = _load_table(engine, ep)
    stmt = table.insert().values(**payload)
    returning = [table.c[f] for f in ep.fields if f in table.c]
    try:
        with engine.begin() as conn:
            if returning:
                row = conn.execute(stmt.returning(*returning)).mappings().first()
                if row is not None:
                    return {k: _jsonable(v) for k, v in dict(row).items()}
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
                    return {k: _jsonable(v) for k, v in dict(row).items()}
            return {k: _jsonable(v) for k, v in payload.items()}
    except IntegrityError as exc:
        raise ValueError("Insert violated a database constraint.") from exc
    except SQLAlchemyError as exc:
        raise ValueError(f"Database error: {exc.__class__.__name__}") from exc


def _mutate_update(info: Any, name: str, item_id: Any, data: dict[str, Any]) -> dict[str, Any]:
    ep = _write_endpoints(info).get(name)
    if ep is None or not ({HttpMethod.PATCH, HttpMethod.PUT} & set(ep.methods)):
        raise ValueError(f"Update not allowed for endpoint '{name}'.")
    if ep.is_sql:
        raise ValueError("SQL endpoints are read-only over GraphQL.")
    engine: Engine = info.context["engine"]
    payload = _filter_write_payload(ep, data)
    if not payload:
        raise ValueError("Update payload must include at least one writable field.")
    table = _load_table(engine, ep)
    pk = ep.primary_key
    if pk not in table.c:
        raise ValueError(f"Primary key '{pk}' missing on table.")
    returning = [table.c[f] for f in ep.fields if f in table.c]
    try:
        with engine.begin() as conn:
            stmt = table.update().where(table.c[pk] == item_id).values(**payload)
            if returning:
                row = conn.execute(stmt.returning(*returning)).mappings().first()
                if row is not None:
                    return {k: _jsonable(v) for k, v in dict(row).items()}
            result = conn.execute(stmt)
            if result.rowcount == 0:
                raise ValueError(f"{name} with {pk}={item_id} not found")
            cols = [table.c[f] for f in ep.fields if f in table.c]
            row = conn.execute(select(*cols).where(table.c[pk] == item_id)).mappings().first()
            if not row:
                raise ValueError(f"{name} with {pk}={item_id} not found")
            return {k: _jsonable(v) for k, v in dict(row).items()}
    except IntegrityError as exc:
        raise ValueError("Update violated a database constraint.") from exc
    except SQLAlchemyError as exc:
        raise ValueError(f"Database error: {exc.__class__.__name__}") from exc


def _mutate_delete(info: Any, name: str, item_id: Any) -> dict[str, Any]:
    ep = _write_endpoints(info).get(name)
    if ep is None or HttpMethod.DELETE not in ep.methods:
        raise ValueError(f"Delete not allowed for endpoint '{name}'.")
    if ep.is_sql:
        raise ValueError("SQL endpoints are read-only over GraphQL.")
    engine: Engine = info.context["engine"]
    table = _load_table(engine, ep)
    pk = ep.primary_key
    if pk not in table.c:
        raise ValueError(f"Primary key '{pk}' missing on table.")
    with engine.begin() as conn:
        if ep.soft_delete and ep.soft_delete.column in table.c:
            from datetime import datetime, timezone

            result = conn.execute(
                table.update()
                .where(table.c[pk] == item_id)
                .values({ep.soft_delete.column: datetime.now(timezone.utc)})
            )
        else:
            result = conn.execute(table.delete().where(table.c[pk] == item_id))
        if result.rowcount == 0:
            raise ValueError(f"{name} with {pk}={item_id} not found")
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
    """
    if not graphql_available() or GraphQLRouter is None or _GRAPHQL_SCHEMA is None:
        return

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

    def context_getter() -> dict[str, Any]:
        return {
            "engine": engine,
            "endpoints": endpoints,
            "write_endpoints": write_endpoints,
            "mutation_ops": mutation_ops,
            "spec": spec,
        }

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
