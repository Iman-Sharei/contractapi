"""GraphQL facade generated from ApiSpec (optional: strawberry)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine

from contractapi.domain.models.spec import ApiSpec, HttpMethod


def graphql_available() -> bool:
    try:
        import strawberry  # noqa: F401

        return True
    except ImportError:
        return False


def mount_graphql(app: Any, engine: Engine, spec: ApiSpec) -> None:
    """
    Mount /graphql scoped to allowlisted table GET endpoints (contract-first).

    Requires: pip install 'contractapi[graphql]'
    Pattern inspired by Hasura/PostGraphile — but only fields declared in YAML.
    """
    if not graphql_available():
        return

    import strawberry
    from strawberry.fastapi import GraphQLRouter
    from strawberry.scalars import JSON

    endpoints = {
        e.name: e for e in spec.endpoints if HttpMethod.GET in e.methods and not e.is_sql
    }
    if not endpoints:
        return

    metadata = MetaData()

    @strawberry.type
    class GqlRow:
        data: JSON

    @strawberry.type
    class Query:
        @strawberry.field
        def endpoint(self, name: str, limit: int = 20) -> list[GqlRow]:
            ep = endpoints.get(name)
            if ep is None:
                raise ValueError(
                    f"Unknown or non-GraphQL endpoint '{name}'. "
                    f"Allowed: {sorted(endpoints)}"
                )
            limit = max(1, min(limit, ep.pagination.max_limit))
            table = Table(ep.table, metadata, schema=ep.schema_name, autoload_with=engine)
            cols = [table.c[c] for c in ep.fields if c in table.c]
            with engine.connect() as conn:
                rows = conn.execute(select(*cols).limit(limit)).mappings().all()
            return [GqlRow(data={k: _jsonable(v) for k, v in dict(r).items()}) for r in rows]

        @strawberry.field
        def available_endpoints(self) -> list[str]:
            return sorted(endpoints)

    schema = strawberry.Schema(query=Query)
    app.include_router(GraphQLRouter(schema), prefix="/graphql")


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
