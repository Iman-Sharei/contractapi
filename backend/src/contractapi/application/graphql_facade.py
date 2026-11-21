"""GraphQL facade generated from ApiSpec (optional: strawberry)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.engine import Engine

from contractapi.application.graphql_mutations import (
    _mutate_create,
    _mutate_delete,
    _mutate_update,
    _mutation_ops,
)
from contractapi.application.graphql_ops import (
    _apply_rbac,
    _effective_roles,
    _fetch_rows,
)
from contractapi.domain.models.spec import ApiSpec, EndpointSpec, HttpMethod
from contractapi.infrastructure.security.auth import enforce_endpoint_roles

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
            "api_name": getattr(app.state, "api_name", None),
        }

    # Postponed annotations: bind the real class so FastAPI injects the connection.
    context_getter.__annotations__["conn"] = HTTPConnection
    app.include_router(
        GraphQLRouter(_GRAPHQL_SCHEMA, context_getter=context_getter),
        prefix="/graphql",
    )


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
