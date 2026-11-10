"""GraphQL facade generated from ApiSpec (optional: strawberry)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Column, MetaData, String, Table, select, text
from sqlalchemy.engine import Engine

from contractapi.domain.models.spec import ApiSpec, EndpointSpec, HttpMethod

try:
    import strawberry
    from strawberry.fastapi import GraphQLRouter
    from strawberry.scalars import JSON
    from strawberry.types import Info

    @strawberry.type
    class Query:
        @strawberry.field
        def endpoint(self, info: Info, name: str, limit: int = 20) -> list[JSON]:
            endpoints: dict[str, EndpointSpec] = info.context["endpoints"]
            engine: Engine = info.context["engine"]
            ep = endpoints.get(name)
            if ep is None:
                raise ValueError(
                    f"Unknown or non-GraphQL endpoint '{name}'. "
                    f"Allowed: {sorted(endpoints)}"
                )
            return _fetch_rows(engine, ep, limit)

        @strawberry.field
        def available_endpoints(self, info: Info) -> list[str]:
            return sorted(info.context["endpoints"])

    _GRAPHQL_SCHEMA = strawberry.Schema(query=Query)
    _GRAPHQL_READY = True
except ImportError:  # pragma: no cover - optional extra
    GraphQLRouter = None  # type: ignore[misc, assignment]
    _GRAPHQL_SCHEMA = None
    _GRAPHQL_READY = False


def graphql_available() -> bool:
    return _GRAPHQL_READY


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


def _fetch_rows(engine: Engine, ep: EndpointSpec, limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(limit, ep.pagination.max_limit))
    try:
        table = _load_table(engine, ep)
        cols = [table.c[c] for c in ep.fields if c in table.c]
        if not cols:
            raise RuntimeError("no columns")
        with engine.connect() as conn:
            rows = conn.execute(select(*cols).limit(limit)).mappings().all()
        return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]
    except Exception:
        fields_sql = ", ".join(f'"{f}"' for f in ep.fields)
        schema = ep.schema_name
        if schema and schema not in {"main", ""}:
            table_sql = f'"{schema}"."{ep.table}"'
        else:
            table_sql = f'"{ep.table}"'
        sql = text(f"SELECT {fields_sql} FROM {table_sql} LIMIT :limit")
        with engine.connect() as conn:
            rows = conn.execute(sql, {"limit": limit}).mappings().all()
        return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]


def mount_graphql(app: Any, engine: Engine, spec: ApiSpec) -> None:
    """
    Mount /graphql scoped to allowlisted table GET endpoints (contract-first).

    GA when strawberry is installed: pip install 'contractapi[graphql]'.
    Pattern inspired by Hasura/PostGraphile — but only fields declared in YAML.
    """
    if not graphql_available() or GraphQLRouter is None or _GRAPHQL_SCHEMA is None:
        return

    endpoints = {
        e.name: e for e in spec.endpoints if HttpMethod.GET in e.methods and not e.is_sql
    }
    if not endpoints:
        return

    def context_getter() -> dict[str, Any]:
        return {"engine": engine, "endpoints": endpoints}

    app.include_router(
        GraphQLRouter(_GRAPHQL_SCHEMA, context_getter=context_getter),
        prefix="/graphql",
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def graphql_status(spec: ApiSpec) -> dict[str, Any]:
    return {
        "available": graphql_available(),
        "install": "pip install 'contractapi[graphql]'",
        "endpoints": [
            e.name for e in spec.endpoints if HttpMethod.GET in e.methods and not e.is_sql
        ],
    }
