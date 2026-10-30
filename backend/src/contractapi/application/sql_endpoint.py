"""Read-only list/detail handlers for EndpointSpec.sql sources."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from contractapi.application.cursor_paging import decode_cursor, encode_cursor
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, EndpointSpec, PaginationMode


_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _quote_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="Misconfigured",
            status=500,
            detail=f"Unsafe identifier: {name}",
        )
    return f'"{name}"'


def _inner_sql(endpoint: EndpointSpec) -> str:
    return (endpoint.sql or "").strip().rstrip(";").strip()


def _build_where(
    request: Request,
    endpoint: EndpointSpec,
    *,
    reserved: set[str],
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    allowed_fields = set(endpoint.filters)
    allowed_ops = set(endpoint.filter_operators)
    idx = 0
    for key, value in request.query_params.multi_items():
        if key in reserved:
            continue
        if "__" in key:
            field, op = key.rsplit("__", 1)
        else:
            field, op = key, "eq"
        if field not in allowed_fields or op not in allowed_ops:
            raise AppError(
                type_="https://contractapi.dev/problems/invalid-filter",
                title="Filter not allowed",
                status=400,
                detail="Only configured filter fields/operators are accepted.",
                extensions={"rejected": key},
            )
        col = f"q.{_quote_ident(field)}"
        pname = f"p{idx}"
        idx += 1
        if op == "eq":
            clauses.append(f"{col} = :{pname}")
            params[pname] = value
        elif op == "ne":
            clauses.append(f"{col} <> :{pname}")
            params[pname] = value
        elif op == "gt":
            clauses.append(f"{col} > :{pname}")
            params[pname] = value
        elif op == "gte":
            clauses.append(f"{col} >= :{pname}")
            params[pname] = value
        elif op == "lt":
            clauses.append(f"{col} < :{pname}")
            params[pname] = value
        elif op == "lte":
            clauses.append(f"{col} <= :{pname}")
            params[pname] = value
        elif op == "contains":
            clauses.append(f"{col} ILIKE :{pname}")
            params[pname] = f"%{value}%"
        elif op == "startswith":
            clauses.append(f"{col} ILIKE :{pname}")
            params[pname] = f"{value}%"
        elif op == "in":
            values = [v for v in value.split(",") if v != ""]
            placeholders = []
            for j, v in enumerate(values):
                pn = f"{pname}_{j}"
                placeholders.append(f":{pn}")
                params[pn] = v
            clauses.append(f"{col} IN ({', '.join(placeholders)})")
        else:
            raise AppError(
                type_="https://contractapi.dev/problems/invalid-filter",
                title="Filter not allowed",
                status=400,
                detail=f"Unknown operator {op}",
            )
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _csv_response(items: list[dict[str, Any]], fields: list[str]) -> PlainTextResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in items:
        writer.writerow({k: row.get(k) for k in fields})
    return PlainTextResponse(buf.getvalue(), media_type="text/csv; charset=utf-8")


def _ndjson_response(items: list[dict[str, Any]], fields: list[str]) -> PlainTextResponse:
    lines = [json.dumps({k: row.get(k) for k in fields}, default=str) for row in items]
    return PlainTextResponse("\n".join(lines) + ("\n" if lines else ""), media_type="application/x-ndjson")


def _parquet_response(items: list[dict[str, Any]], fields: list[str]) -> Response:
    """Serialize rows as Apache Parquet (requires optional pyarrow)."""
    from contractapi.core.config import get_settings

    if not get_settings().experimental_enabled("parquet"):
        raise AppError(
            type_="https://contractapi.dev/problems/experimental-disabled",
            title="Parquet disabled",
            status=501,
            detail="Enable with CONTRACTAPI_EXPERIMENTAL=parquet (or all)",
        )
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/dependency-missing",
            title="Parquet support not installed",
            status=501,
            detail="Install with: pip install 'contractapi[parquet]'",
        ) from exc

    columns = {f: [row.get(f) for row in items] for f in fields}
    # Normalize non-Arrow-native values to strings
    for key, values in columns.items():
        columns[key] = [v if v is None or isinstance(v, (bool, int, float, str, bytes)) else str(v) for v in values]
    table = pa.table(columns)
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="zstd")
    return Response(
        content=sink.getvalue(),
        media_type="application/vnd.apache.parquet",
        headers={"Content-Disposition": 'attachment; filename="export.parquet"'},
    )


def bind_sql_params(endpoint: EndpointSpec, request: Request) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for param in endpoint.sql_params:
        raw = request.query_params.get(param.name)
        if raw is None or raw == "":
            if param.required and param.default is None:
                raise AppError(
                    type_="https://contractapi.dev/problems/validation-error",
                    title="Validation failed",
                    status=422,
                    detail=f"Missing required SQL param '{param.name}'.",
                )
            if param.default is not None:
                out[param.name] = param.default
            continue
        if param.type == "int":
            out[param.name] = int(raw)
        elif param.type == "float":
            out[param.name] = float(raw)
        elif param.type == "bool":
            out[param.name] = raw.lower() in {"1", "true", "yes", "on"}
        else:
            out[param.name] = raw
    return out


def mount_sql_endpoint(
    router: APIRouter,
    engine: Engine,
    endpoint: EndpointSpec,
    spec: ApiSpec,
) -> None:
    # Lazy import to avoid circular dependency with data_api_builder.
    from contractapi.application import data_api_builder as dab

    tags = [endpoint.name]
    max_limit = endpoint.pagination.max_limit
    default_limit = endpoint.pagination.default_limit
    reserved = {"limit", "offset", "sort", "cursor", "include_total", "fields", "format"}
    reserved |= {p.name for p in endpoint.sql_params}
    select_list = ", ".join(f"q.{_quote_ident(f)}" for f in endpoint.fields)
    inner = _inner_sql(endpoint)

    async def list_items(
        request: Request,
        limit: int = Query(default=default_limit, ge=1, le=max_limit),
        offset: int = Query(default=0, ge=0),
        cursor: str | None = Query(default=None),
        sort: str | None = Query(default=None),
        include_total: bool = Query(default=False),
        format: str | None = Query(default=None),  # noqa: A002
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
                if include_total or mode != PaginationMode.CURSOR:
                    where_only, filter_params = _build_where(request, endpoint, reserved=reserved)
                    count_sql = f"SELECT COUNT(*) FROM ({inner}) AS q{where_only}"
                    total = int(
                        conn.execute(text(count_sql), {**filter_params, **sql_bind}).scalar_one()
                    )
                rows = conn.execute(text(page_sql), params).mappings().all()
        except SQLAlchemyError as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/database-error",
                title="Database error",
                status=500,
                detail=exc.__class__.__name__,
            ) from exc

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

    async def get_item(request: Request, item_id: Any) -> Any:
        fields = dab._visible_fields(spec, endpoint, request)
        sql = (
            f"SELECT {select_list} FROM ({inner}) AS q "
            f"WHERE q.{_quote_ident(pk)} = :id LIMIT 1"
        )
        try:
            with engine.connect() as conn:
                row = conn.execute(text(sql), {"id": item_id}).mappings().first()
        except SQLAlchemyError as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/database-error",
                title="Database error",
                status=500,
                detail=exc.__class__.__name__,
            ) from exc
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
        result = conn.execute(q, bind or {})
        return list(result.keys())
