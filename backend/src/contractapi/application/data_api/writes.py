"""Generated POST/bulk/PATCH/PUT/DELETE endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, create_model
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.application.data_api.common import (
    _audit,
    _bind_path_type,
    _check_if_match,
    _etag_for,
    _fetch_row,
    _invalidate_endpoint_cache,
    _job_owner,
    _json_response,
    _model_name,
    _project_fields,
    _python_type,
    _rbac_fields,
    _row_to_dict,
    _visible_fields,
)
from contractapi.application.data_api.write_support import (
    _bind_body,
    _created_location,
    _do_insert,
    _idempotency_begin,
    _idempotency_commit,
    _idempotency_replay_or_conflict,
    _inject_row_level,
    _validate_write_body,
)
from contractapi.application.jobs import create_job, enqueue_job
from contractapi.application.query_filters import combine
from contractapi.application.row_security import apply_security_clauses
from contractapi.application.validation_rules import validate_payload
from contractapi.core.errors import (
    AppError,
)
from contractapi.domain.models.spec import (
    HttpMethod,
)
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.webhooks import dispatch_webhooks


def _add_create(router, engine, table, endpoint, spec, item_model, write_model, tags) -> None:  # type: ignore[no-untyped-def]
    def create_item(request: Request, body: Any = Body(...)) -> Any:
        visible = _visible_fields(spec, endpoint, request)  # role gate before any side effect
        payload = _validate_write_body(body, write_model)
        validate_payload(endpoint, payload)
        payload = _inject_row_level(endpoint, request, payload)
        path = endpoint.path
        store_key = _idempotency_begin(
            request, spec=spec, endpoint=endpoint, method="POST", path=path, payload=payload
        )
        if store_key:
            replay = _idempotency_replay_or_conflict(store_key, method="POST", path=path, payload=payload, request=request)
            if replay is not None:
                return replay

        if endpoint.async_writes:
            job_payload = {
                # Unresolved URL: may hold ${secret:…}/${env:…} refs, resolved by the worker.
                "database_url": spec.database.url,
                "driver": spec.database.driver.value,
                "table": endpoint.table,
                "schema": endpoint.schema_name,
                "fields": endpoint.fields,
                "primary_key": endpoint.primary_key,
                "endpoint_name": endpoint.name,
                "path": endpoint.path,
                "row": payload,
            }
            job = create_job(kind="insert", payload=job_payload, owner=_job_owner(spec, request))

            def work() -> dict[str, Any]:
                result = _do_insert(engine, table, endpoint, payload)
                _invalidate_endpoint_cache(spec, endpoint)
                return _project_fields(result, visible, [])

            enqueue_job(job.id, work)
            _audit(spec, "create.async", endpoint, request, status=202, resource_id=None, meta={"job_id": job.id})
            return _json_response(
                {"job_id": job.id, "status": "queued"},
                status_code=202,
                headers={"Location": f"/jobs/{job.id}"},
            )

        result = _do_insert(engine, table, endpoint, payload)
        body_out = _project_fields(result, visible, [])
        new_id = result.get(endpoint.primary_key)
        headers = {"ETag": _etag_for(result, endpoint), "Location": _created_location(endpoint, new_id)}
        _invalidate_endpoint_cache(spec, endpoint)
        _idempotency_commit(
            store_key,
            method="POST",
            path=path,
            payload=payload,
            status_code=201,
            body=body_out,
            ttl_seconds=spec.app.idempotency.ttl_seconds,
        )
        _audit(spec, "create", endpoint, request, status=201, resource_id=new_id)
        dispatch_webhooks(spec, event="create", endpoint=endpoint.name, payload=result)
        return _json_response(body_out, status_code=201, headers=headers)

    create_item.__name__ = f"create_{endpoint.name}"
    _bind_body(create_item, write_model)
    router.add_api_route(
        endpoint.path,
        create_item,
        methods=["POST"],
        status_code=201,
        tags=tags,
        summary=f"Create {endpoint.name}",
        name=f"create_{endpoint.name}",
    )


def _add_bulk(router, engine, table, endpoint, spec, write_model, tags) -> None:  # type: ignore[no-untyped-def]
    bulk_model = create_model(
        f"{_model_name(endpoint.name)}Bulk",
        items=(list[dict[str, Any]], Field(..., max_length=100)),
    )

    def bulk_create(request: Request, body: Any = Body(...)) -> Any:
        visible = _visible_fields(spec, endpoint, request)
        if isinstance(body, BaseModel):
            body = body.model_dump()
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail='Body must be {"items": [ ... ]}.',
            )
        if len(body["items"]) > 100:
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail="Bulk max 100 items.",
            )

        created: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for idx, item in enumerate(body["items"]):
            try:
                payload = _validate_write_body(item, write_model)
                validate_payload(endpoint, payload)
                payload = _inject_row_level(endpoint, request, payload)
                created.append(_do_insert(engine, table, endpoint, payload))
            except AppError as exc:
                errors.append({"index": idx, "status": exc.status, "detail": exc.detail})

        if created:
            _invalidate_endpoint_cache(spec, endpoint)
        _audit(
            spec,
            "bulk_create",
            endpoint,
            request,
            status=207 if errors else 201,
            meta={"created": len(created), "errors": len(errors)},
        )
        status = 201 if not errors else (207 if created else 422)
        items_out = [_project_fields(r, visible, []) for r in created]
        return _json_response({"items": items_out, "errors": errors}, status_code=status)

    bulk_create.__name__ = f"bulk_create_{endpoint.name}"
    _bind_body(bulk_create, bulk_model)
    router.add_api_route(
        f"{endpoint.path}/bulk",
        bulk_create,
        methods=["POST"],
        tags=tags,
        summary=f"Bulk create {endpoint.name} (max 100)",
        name=f"bulk_create_{endpoint.name}",
    )


def _add_update(router, engine, table, endpoint, spec, item_model, write_model, tags) -> None:  # type: ignore[no-untyped-def]
    pk = endpoint.primary_key
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
        stmt = (
            table.update()
            .where(combine(clauses))
            .values(**payload)
            .returning(*(table.c[f] for f in endpoint.fields))
        )
        try:
            with engine.begin() as conn:
                row = conn.execute(stmt).fetchone()
        except IntegrityError as exc:
            raise AppError(
                type_="https://contractapi.dev/problems/conflict",
                title="Conflict",
                status=409,
                detail="Update violated a database constraint.",
            ) from exc
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
                        .values({endpoint.soft_delete.column: datetime.now(timezone.utc)})
                    )
                    result = conn.execute(stmt)
                else:
                    result = conn.execute(table.delete().where(where))
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
