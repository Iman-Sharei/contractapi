"""Generated GET list/detail endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import MetaData, Table, asc, desc, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from contractapi.application.cursor_paging import check_cursor_sort, decode_cursor, encode_cursor
from contractapi.application.data_api.common import (
    _bind_path_type,
    _cache_prefix,
    _check_if_none_match,
    _etag_for,
    _fetch_row,
    _json_response,
    _pagination_link_header,
    _project_fields,
    _python_type,
    _rbac_fields,
    _row_scope,
    _row_to_dict,
    _select_relations,
    _visible_fields,
)
from contractapi.application.query_filters import combine, parse_filters
from contractapi.application.relations import load_relations
from contractapi.application.row_security import apply_security_clauses
from contractapi.core.errors import (
    AppError,
)
from contractapi.domain.models.spec import (
    ApiSpec,
    EndpointSpec,
    PaginationMode,
)
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.observability import metrics


def _wants_export(endpoint: EndpointSpec, request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    fmt = request.query_params.get("format")
    return (
        (endpoint.csv_export and (fmt == "csv" or "text/csv" in accept))
        or (endpoint.ndjson_export and (fmt == "ndjson" or "ndjson" in accept))
        or (endpoint.parquet_export and (fmt == "parquet" or "parquet" in accept))
    )


def _list_headers(endpoint: EndpointSpec, link: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if link:
        headers["Link"] = link
    if endpoint.deprecation.deprecated:
        headers["Deprecation"] = "true"
        if endpoint.deprecation.sunset:
            headers["Sunset"] = endpoint.deprecation.sunset
    return headers


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
    [r.name for r in endpoint.relations]
    reserved = {
        "limit",
        "offset",
        "sort",
        "cursor",
        "include_total",
        "fields",
        "format",
        "include",
        "expand",
    }

    def list_items(
        request: Request,
        limit: int = Query(default=default_limit, ge=1, le=max_limit),
        offset: int = Query(default=0, ge=0),
        cursor: str | None = Query(default=None),
        sort: str | None = Query(default=None),
        include_total: bool = Query(default=False),
        include: str | None = Query(
            default=None,
            description="Comma-separated relation names to embed (* or omit = all).",
        ),
        expand: str | None = Query(
            default=None,
            description="Alias of include.",
        ),
    ) -> Any:
        fields = _visible_fields(spec, endpoint, request)
        if not endpoint.pagination.enabled:
            limit, offset, cursor = max_limit, 0, None

        cache_key = (
            f"{_cache_prefix(spec, endpoint)}{_row_scope(endpoint, request)}"
            f"list:{request.url.query}:fields={','.join(fields)}"
        )
        # The cache holds JSON pages only; CSV/NDJSON/Parquet requests always build fresh.
        if spec.app.cache.enabled and not _wants_export(endpoint, request):
            cached = response_cache.get(cache_key)
            if cached is not None:
                metrics.incr("contractapi_cache_hits_total", labels={"endpoint": endpoint.name})
                # Links are rebuilt per request: the same data is served under /data and
                # /apis/<name>, possibly via different hosts — a cached absolute URL would be wrong.
                link = _pagination_link_header(
                    request,
                    mode=endpoint.pagination.mode,
                    limit=cached.get("limit", limit),
                    offset=cached.get("offset", 0),
                    total=cached.get("total"),
                    next_cursor=cached.get("next_cursor"),
                )
                return _json_response(cached, headers=_list_headers(endpoint, link))
            metrics.incr("contractapi_cache_misses_total", labels={"endpoint": endpoint.name})

        # Filters/sort only on fields this caller may see — else hidden values leak by inference.
        rbac_visible = set(_rbac_fields(spec, endpoint, request))
        filter_clauses = parse_filters(
            list(request.query_params.multi_items()),
            table=table,
            endpoint=endpoint,
            reserved=reserved,
            visible=rbac_visible,
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
            check_cursor_sort(sort, endpoint.primary_key)
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
                raise db_error(exc) from exc

            has_more = len(rows) > limit
            rows = rows[:limit]
            items = [_row_to_dict(r, endpoint.fields) for r in rows]
            if has_more and items:
                next_cursor = encode_cursor(items[-1][endpoint.primary_key])
        else:
            pk_col = table.c[endpoint.primary_key]
            if sort:
                descending = sort.startswith("-")
                col_name = sort[1:] if descending else sort
                sortable_now = allowed_sort & rbac_visible
                if col_name not in sortable_now:
                    raise AppError(
                        type_="https://contractapi.dev/problems/invalid-sort",
                        title="Sort field not allowed",
                        status=400,
                        detail="Only configured sortable fields are accepted.",
                        extensions={"allowed": sorted(sortable_now), "rejected": col_name},
                    )
                stmt = stmt.order_by(
                    desc(table.c[col_name]) if descending else asc(table.c[col_name])
                )
            # Deterministic paging: always end with the primary key as tie-breaker.
            stmt = stmt.order_by(asc(pk_col))
            try:
                with engine.connect() as conn:
                    count_stmt = select(func.count()).select_from(table)
                    if where is not None:
                        count_stmt = count_stmt.where(where)
                    total = int(conn.execute(count_stmt).scalar_one())
                    rows = conn.execute(stmt.limit(limit).offset(offset)).fetchall()
            except SQLAlchemyError as exc:
                raise db_error(exc) from exc
            items = [_row_to_dict(r, endpoint.fields) for r in rows]

        active_relations = _select_relations(endpoint, include or expand)
        if active_relations and items:
            try:
                load_relations(engine, metadata, active_relations, items)
            except Exception as exc:
                raise AppError(
                    type_="https://contractapi.dev/problems/relation-error",
                    title="Relation load failed",
                    status=500,
                    detail="Nested data could not be loaded. Check the relation settings in Studio.",
                ) from exc

        projected = [
            _project_fields(i, fields, [r.name for r in active_relations]) for i in items
        ]
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
            from contractapi.application.exports import _csv_response

            return _csv_response(projected, fields)
        if endpoint.ndjson_export and (
            fmt == "ndjson" or "application/x-ndjson" in accept or "application/ndjson" in accept
        ):
            from contractapi.application.exports import _ndjson_response

            return _ndjson_response(projected, fields)
        if endpoint.parquet_export and (
            fmt == "parquet"
            or "application/vnd.apache.parquet" in accept
            or "application/parquet" in accept
        ):
            from contractapi.application.exports import _parquet_response

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
            response_cache.set(cache_key, payload, spec.app.cache.ttl_seconds)

        return _json_response(payload, headers=_list_headers(endpoint, link))

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

    def get_item(request: Request, item_id: Any) -> Any:
        fields = _visible_fields(spec, endpoint, request)
        cache_key = (
            f"{_cache_prefix(spec, endpoint)}{_row_scope(endpoint, request)}"
            f"detail:{item_id}:fields={','.join(fields)}"
        )
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
                raise db_error(exc) from exc
            if item is None:
                raise AppError(
                    type_="https://contractapi.dev/problems/not-found",
                    title="Not Found",
                    status=404,
                    detail=f"{endpoint.name} with {pk}={item_id} not found",
                )
            # ETag from the stored row (same basis as PATCH/PUT/DELETE If-Match), not the
            # projected view — otherwise relations/RBAC/sparse fields break concurrency control.
            etag = _etag_for(item, endpoint)
            if endpoint.relations:
                try:
                    load_relations(engine, metadata, endpoint.relations, [item])
                except SQLAlchemyError as exc:
                    raise AppError(
                        type_="https://contractapi.dev/problems/relation-error",
                        title="Relation load failed",
                        status=500,
                        detail="Nested data could not be loaded. Check the relation settings in Studio.",
                    ) from exc
            projected = _project_fields(item, fields, rel_names)
            if spec.app.cache.enabled:
                response_cache.set(
                    cache_key, {"body": projected, "etag": etag}, spec.app.cache.ttl_seconds
                )
        else:
            projected, etag = cached["body"], cached["etag"]

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
