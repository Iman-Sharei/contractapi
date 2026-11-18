"""Read-only list/detail handlers for EndpointSpec.sql sources."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from contractapi.application.cursor_paging import decode_cursor, encode_cursor
from contractapi.application.exports import (
    _csv_response,
    _ndjson_response,
    _parquet_response,
)
from contractapi.application.sql_filters import (
    _build_where,
    _quote_ident,
    bind_sql_params,
)
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, EndpointSpec, PaginationMode
from contractapi.infrastructure.db.errors import db_error


def begin_read_only(conn: Any) -> None:
    """Postgres: run custom SQL in a READ ONLY transaction, so even side-effecting
    functions (nextval, pg_terminate_backend, dblink_exec…) cannot change data.
    Must be the first statement of the transaction. Other drivers keep the keyword guard."""
    if conn.dialect.name == "postgresql":
        conn.execute(text("SET TRANSACTION READ ONLY"))


def _inner_sql(endpoint: EndpointSpec) -> str:
    return (endpoint.sql or "").strip().rstrip(";").strip()


def mount_sql_endpoint(
    router: APIRouter,
    engine: Engine,
    endpoint: EndpointSpec,
    spec: ApiSpec,
) -> None:
    # Lazy import to avoid a circular dependency with the data_api package.
    from contractapi.application.data_api import common as dab

    tags = [endpoint.name]
    max_limit = endpoint.pagination.max_limit
    default_limit = endpoint.pagination.default_limit
    reserved = {"limit", "offset", "sort", "cursor", "include_total", "fields", "format"}
    reserved |= {p.name for p in endpoint.sql_params}
    select_list = ", ".join(f"q.{_quote_ident(f)}" for f in endpoint.fields)
    inner = _inner_sql(endpoint)

    def list_items(
        request: Request,
        limit: int = Query(default=default_limit, ge=1, le=max_limit),
        offset: int = Query(default=0, ge=0),
        cursor: str | None = Query(default=None),
        sort: str | None = Query(default=None),
        include_total: bool = Query(default=False),
        format: str | None = Query(default=None),
    ) -> Any:
        fields = dab._visible_fields(spec, endpoint, request)
        if not endpoint.pagination.enabled:
            limit, offset, cursor = max_limit, 0, None

        sql_bind = bind_sql_params(endpoint, request)
        where_sql, params = _build_where(request, endpoint, reserved=reserved)
        params.update(sql_bind)
        mode = endpoint.pagination.mode
        order_sql = f" ORDER BY q.{_quote_ident(endpoint.primary_key)} ASC"
        if sort and mode != PaginationMode.CURSOR:
            descending = sort.startswith("-")
            col = sort[1:] if descending else sort
            if col not in set(endpoint.sortable):
                raise AppError(
                    type_="https://contractapi.dev/problems/invalid-sort",
                    title="Sort field not allowed",
                    status=400,
                    detail="Only configured sortable fields are accepted.",
                )
            order_sql = f" ORDER BY q.{_quote_ident(col)} {'DESC' if descending else 'ASC'}"

        if mode == PaginationMode.CURSOR and cursor:
            try:
                cursor_val = decode_cursor(cursor)
            except Exception as exc:
                raise AppError(
                    type_="https://contractapi.dev/problems/invalid-cursor",
                    title="Invalid cursor",
                    status=400,
                    detail="Cursor could not be decoded.",
                ) from exc
            extra = f"q.{_quote_ident(endpoint.primary_key)} > :_cursor"
            where_sql = f"{where_sql} AND {extra}" if where_sql else f" WHERE {extra}"
            params["_cursor"] = cursor_val

        base = f"SELECT {select_list} FROM ({inner}) AS q{where_sql}{order_sql}"
        fetch_limit = limit + 1 if mode == PaginationMode.CURSOR else limit
        page_sql = f"{base} LIMIT :_limit"
        params["_limit"] = fetch_limit
        if mode != PaginationMode.CURSOR:
            page_sql += " OFFSET :_offset"
            params["_offset"] = offset

        total = None
        try:
            with engine.connect() as conn:
                begin_read_only(conn)
                if include_total or mode != PaginationMode.CURSOR:
                    where_only, filter_params = _build_where(request, endpoint, reserved=reserved)
                    count_sql = f"SELECT COUNT(*) FROM ({inner}) AS q{where_only}"
                    total = int(
                        conn.execute(text(count_sql), {**filter_params, **sql_bind}).scalar_one()
                    )
                rows = conn.execute(text(page_sql), params).mappings().all()
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc

        next_cursor = None
        if mode == PaginationMode.CURSOR:
            has_more = len(rows) > limit
            rows = rows[:limit]
            items = [dab._serialize(dict(r)) for r in rows]
            if has_more and items:
                next_cursor = encode_cursor(items[-1][endpoint.primary_key])
        else:
            items = [dab._serialize(dict(r)) for r in rows]

        projected = [dab._project_fields(i, fields, []) for i in items]
        accept = (request.headers.get("accept") or "").lower()
        if endpoint.csv_export and (format == "csv" or "text/csv" in accept):
            return _csv_response(projected, fields)
        if endpoint.ndjson_export and (
            format == "ndjson" or "application/x-ndjson" in accept or "application/ndjson" in accept
        ):
            return _ndjson_response(projected, fields)
        if endpoint.parquet_export and (
            format == "parquet" or "application/vnd.apache.parquet" in accept or "application/parquet" in accept
        ):
            return _parquet_response(projected, fields)

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

        link = dab._pagination_link_header(
            request,
            mode=mode,
            limit=limit,
            offset=offset,
            total=total,
            next_cursor=next_cursor,
        )
        headers = {"Link": link} if link else {}
        return dab._json_response(payload, headers=headers)

    list_items.__name__ = f"list_{endpoint.name}"
    router.add_api_route(
        endpoint.path,
        list_items,
        methods=["GET"],
        tags=tags,
        summary=endpoint.description or f"List {endpoint.name} (SQL)",
        name=f"list_{endpoint.name}",
    )

    pk = endpoint.primary_key

    def get_item(request: Request, item_id: Any) -> Any:
        fields = dab._visible_fields(spec, endpoint, request)
        sql = (
            f"SELECT {select_list} FROM ({inner}) AS q "
            f"WHERE q.{_quote_ident(pk)} = :id LIMIT 1"
        )
        try:
            with engine.connect() as conn:
                begin_read_only(conn)
                row = conn.execute(text(sql), {"id": item_id}).mappings().first()
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc
        if row is None:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        projected = dab._project_fields(dab._serialize(dict(row)), fields, [])
        etag = dab._etag_for(projected, endpoint)
        if request.headers.get("If-None-Match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        wants_csv = endpoint.csv_export and (
            request.query_params.get("format") == "csv"
            or "text/csv" in (request.headers.get("accept") or "").lower()
        )
        if wants_csv:
            return _csv_response([projected], fields)
        return dab._json_response(projected, headers={"ETag": etag})

    get_item.__name__ = f"get_{endpoint.name}"
    dab._bind_path_type(get_item, "item_id", str)
    router.add_api_route(
        f"{endpoint.path}/{{item_id}}",
        get_item,
        methods=["GET"],
        tags=tags,
        summary=f"Get {endpoint.name}",
        name=f"get_{endpoint.name}",
    )


def preview_sql_columns(
    engine: Engine,
    sql: str,
    *,
    bind: dict[str, Any] | None = None,
) -> list[str]:
    from contractapi.domain.models.spec import _assert_safe_select

    _assert_safe_select(sql, endpoint_name="preview")
    inner = sql.strip().rstrip(";").strip()
    q = text(f"SELECT * FROM ({inner}) AS q LIMIT 0")
    with engine.connect() as conn:
        begin_read_only(conn)
        result = conn.execute(q, bind or {})
        return list(result.keys())
