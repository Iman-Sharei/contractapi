"""Generated PATCH/PUT/DELETE endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Request
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.application.data_api.common import (
    _audit,
    _bind_path_type,
    _check_if_match,
    _etag_for,
    _fetch_row,
    _invalidate_endpoint_cache,
    _json_response,
    _project_fields,
    _python_type,
    _rbac_fields,
    _row_to_dict,
    _visible_fields,
)
from contractapi.application.data_api.write_rules import db_timezone, for_update, now_for
from contractapi.application.data_api.write_support import (
    IN_USE_DETAIL,
    _bind_body,
    _idempotency_begin,
    _idempotency_commit,
    _idempotency_replay_or_conflict,
    _inject_row_level,
    _validate_write_body,
    conflict_error,
)
from contractapi.application.query_filters import combine
from contractapi.application.row_security import apply_security_clauses
from contractapi.application.validation_rules import validate_payload
from contractapi.core.errors import (
    AppError,
)
from contractapi.domain.models.spec import (
    HttpMethod,
)
from contractapi.infrastructure.db.dialects import update_returning
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.webhooks import dispatch_webhooks


def _add_update(router, engine, table, endpoint, spec, item_model, write_model, tags) -> None:  # type: ignore[no-untyped-def]
    pk = endpoint.primary_key
    tz = db_timezone(spec)
    pk_type = _python_type(table.c[pk].type)

    def _update(request: Request, item_id: Any, body: Any, method: str) -> Any:
        visible = _visible_fields(spec, endpoint, request)
        payload = _validate_write_body(body, write_model)
        if not payload:
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail="Request body must include at least one field.",
            )
        if method == "PUT":
            # PUT replaces the resource: every writable field must be sent (use PATCH for partial).
            owner = endpoint.row_level.column if endpoint.row_level else None
            missing = [f for f in endpoint.writable_fields if f not in payload and f != owner]
            if missing:
                raise AppError(
                    type_="https://contractapi.dev/problems/validation-error",
                    title="Validation failed",
                    status=422,
                    detail="PUT replaces the whole resource; send every writable field or use PATCH.",
                    extensions={"missing": missing},
                )
        validate_payload(endpoint, payload)
        # Prevent changing ownership column away from claim
        if endpoint.row_level and endpoint.row_level.column in payload:
            payload = _inject_row_level(endpoint, request, payload)

        path = f"{endpoint.path}/{item_id}"
        store_key = _idempotency_begin(
            request, spec=spec, endpoint=endpoint, method=method, path=path, payload=payload
        )
        if store_key:
            replay = _idempotency_replay_or_conflict(store_key, method=method, path=path, payload=payload, request=request)
            if replay is not None:
                return replay

        current = _fetch_row(engine, table, endpoint, request, item_id)
        if current is None:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        _check_if_match(request, _etag_for(current, endpoint))

        clauses = apply_security_clauses([table.c[pk] == item_id], table, endpoint, request)
        values = for_update(endpoint, table, payload, tz)
        try:
            with engine.begin() as conn:
                row = update_returning(conn, table, combine(clauses), values, endpoint.fields)
        except IntegrityError as exc:
            raise conflict_error(exc) from exc
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc
        if row is None:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        result = _row_to_dict(row, endpoint.fields)
        body_out = _project_fields(result, visible, [])
        _invalidate_endpoint_cache(spec, endpoint)
        _idempotency_commit(
            store_key,
            method=method,
            path=path,
            payload=payload,
            status_code=200,
            body=body_out,
            ttl_seconds=spec.app.idempotency.ttl_seconds,
        )
        _audit(spec, "update", endpoint, request, status=200, resource_id=item_id)
        dispatch_webhooks(spec, event="update", endpoint=endpoint.name, payload=result)
        return _json_response(body_out, headers={"ETag": _etag_for(result, endpoint)})

    if HttpMethod.PATCH in endpoint.methods:

        def patch_item(request: Request, item_id: Any, body: Any = Body(...)) -> Any:
            return _update(request, item_id, body, "PATCH")

        patch_item.__name__ = f"update_{endpoint.name}"
        _bind_path_type(patch_item, "item_id", pk_type)
        _bind_body(patch_item, write_model)
        router.add_api_route(
            f"{endpoint.path}/{{item_id}}",
            patch_item,
            methods=["PATCH"],
            tags=tags,
            summary=f"Update {endpoint.name} (partial)",
            name=f"update_{endpoint.name}",
        )
    if HttpMethod.PUT in endpoint.methods:

        def put_item(request: Request, item_id: Any, body: Any = Body(...)) -> Any:
            return _update(request, item_id, body, "PUT")

        put_item.__name__ = f"replace_{endpoint.name}"
        _bind_path_type(put_item, "item_id", pk_type)
        _bind_body(put_item, write_model)
        router.add_api_route(
            f"{endpoint.path}/{{item_id}}",
            put_item,
            methods=["PUT"],
            tags=tags,
            summary=f"Replace {endpoint.name} (all writable fields)",
            name=f"replace_{endpoint.name}",
        )


def _add_delete(router, engine, table, endpoint, spec, tags) -> None:  # type: ignore[no-untyped-def]
    pk = endpoint.primary_key
    tz = db_timezone(spec)
    pk_type = _python_type(table.c[pk].type)

    def delete_item(request: Request, item_id: Any) -> Response:
        _rbac_fields(spec, endpoint, request)  # endpoint role gate
        path = f"{endpoint.path}/{item_id}"
        payload = {"id": item_id}
        store_key = _idempotency_begin(
            request, spec=spec, endpoint=endpoint, method="DELETE", path=path, payload=payload
        )
        if store_key:
            replay = _idempotency_replay_or_conflict(store_key, method="DELETE", path=path, payload=payload, request=request)
            if replay is not None:
                return replay

        current = _fetch_row(engine, table, endpoint, request, item_id)
        if current is None:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        _check_if_match(request, _etag_for(current, endpoint))

        clauses = apply_security_clauses([table.c[pk] == item_id], table, endpoint, request)
        where = combine(clauses)
        try:
            with engine.begin() as conn:
                if endpoint.soft_delete and endpoint.soft_delete.column in table.c:
                    stmt = (
                        table.update()
                        .where(where)
                        .values({endpoint.soft_delete.column: now_for(table, endpoint.soft_delete.column, tz)})
                    )
                    result = conn.execute(stmt)
                else:
                    result = conn.execute(table.delete().where(where))
        except IntegrityError as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/conflict",
                title="Conflict",
                status=409,
                detail=IN_USE_DETAIL,
            ) from exc
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc
        if result.rowcount == 0:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Not Found",
                status=404,
                detail=f"{endpoint.name} with {pk}={item_id} not found",
            )
        _invalidate_endpoint_cache(spec, endpoint)
        _idempotency_commit(
            store_key,
            method="DELETE",
            path=path,
            payload=payload,
            status_code=204,
            body=None,
            ttl_seconds=spec.app.idempotency.ttl_seconds,
        )
        _audit(spec, "delete", endpoint, request, status=204, resource_id=item_id)
        dispatch_webhooks(
            spec,
            event="delete",
            endpoint=endpoint.name,
            payload={"id": item_id},
        )
        return Response(status_code=204)

    delete_item.__name__ = f"delete_{endpoint.name}"
    _bind_path_type(delete_item, "item_id", pk_type)
    router.add_api_route(
        f"{endpoint.path}/{{item_id}}",
        delete_item,
        methods=["DELETE"],
        response_class=Response,
        status_code=204,
        tags=tags,
        name=f"delete_{endpoint.name}",
    )
