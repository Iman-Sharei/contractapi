"""Generated POST/bulk/PATCH/PUT/DELETE endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import Body, Request
from pydantic import BaseModel, Field, create_model
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.application.data_api.common import (
    _audit,
    _etag_for,
    _invalidate_endpoint_cache,
    _json_response,
    _model_name,
    _project_fields,
    _row_to_dict,
    _visible_fields,
)
from contractapi.application.data_api.http_meta import (
    _job_owner,
)
from contractapi.application.data_api.write_rules import db_timezone, for_create, split_nested
from contractapi.application.data_api.write_support import (
    _bind_body,
    _created_location,
    _do_insert,
    _idempotency_begin,
    _idempotency_commit,
    _idempotency_replay_or_conflict,
    _inject_row_level,
    _validate_write_body,
    conflict_error,
)
from contractapi.application.jobs import create_job, enqueue_job
from contractapi.application.validation_rules import validate_payload
from contractapi.core.errors import (
    AppError,
)
from contractapi.infrastructure.db.dialects import insert_returning
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.webhooks import dispatch_webhooks


def _add_create(  # type: ignore[no-untyped-def]
    router, engine, table, endpoint, spec, item_model, write_model, tags,
    *, create_model=None, nested=None, unique_sets=(),
):
    body_model = create_model or write_model
    tz = db_timezone(spec)

    def create_item(request: Request, body: Any = Body(...)) -> Any:
        visible = _visible_fields(spec, endpoint, request)  # role gate before any side effect
        payload, children = split_nested(endpoint, _validate_write_body(body, body_model))
        validate_payload(endpoint, payload)
        payload = for_create(endpoint, table, _inject_row_level(endpoint, request, payload), tz)
        idem_payload = {**payload, **children} if children else payload
        path = endpoint.path
        store_key = _idempotency_begin(
            request, spec=spec, endpoint=endpoint, method="POST", path=path, payload=idem_payload
        )
        if store_key:
            replay = _idempotency_replay_or_conflict(
                store_key, method="POST", path=path, payload=idem_payload, request=request
            )
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
                "row": _jsonable_row(payload),
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
                headers={"Location": f"{request.scope.get('root_path') or ''}/jobs/{job.id}"},
            )

        result = _do_insert(
            engine, table, endpoint, payload,
            children=children, nested=nested, unique_sets=unique_sets,
        )
        body_out = _project_fields(result, visible, list(children))
        new_id = result.get(endpoint.primary_key)
        headers = {"ETag": _etag_for(result, endpoint), "Location": _created_location(endpoint, new_id)}
        _invalidate_endpoint_cache(spec, endpoint)
        _idempotency_commit(
            store_key,
            method="POST",
            path=path,
            payload=idem_payload,
            status_code=201,
            body=body_out,
            ttl_seconds=spec.app.idempotency.ttl_seconds,
        )
        _audit(spec, "create", endpoint, request, status=201, resource_id=new_id)
        dispatch_webhooks(spec, event="create", endpoint=endpoint.name, payload=result)
        return _json_response(body_out, status_code=201, headers=headers)

    create_item.__name__ = f"create_{endpoint.name}"
    _bind_body(create_item, body_model)
    router.add_api_route(
        endpoint.path,
        create_item,
        methods=["POST"],
        status_code=201,
        tags=tags,
        summary=f"Create {endpoint.name}",
        name=f"create_{endpoint.name}",
    )


def _add_bulk(router, engine, table, endpoint, spec, write_model, tags, *, unique_sets=()) -> None:  # type: ignore[no-untyped-def]
    tz = db_timezone(spec)
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
        payloads: list[tuple[int, dict[str, Any]]] = []
        for idx, item in enumerate(body["items"]):
            try:
                payload = _validate_write_body(item, write_model)
                validate_payload(endpoint, payload)
                payload = for_create(endpoint, table, _inject_row_level(endpoint, request, payload), tz)
                if endpoint.bulk_atomic:
                    payloads.append((idx, payload))
                else:
                    created.append(_do_insert(engine, table, endpoint, payload, unique_sets=unique_sets))
            except AppError as exc:
                errors.append({"index": idx, "status": exc.status, "detail": exc.detail})

        if endpoint.bulk_atomic:
            if errors:  # all or nothing: nothing was written
                return _json_response({"items": [], "errors": errors}, status_code=422)
            created, failure = _insert_all(engine, table, endpoint, payloads)
            if failure:
                return _json_response({"items": [], "errors": [failure]}, status_code=failure["status"])

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
        summary=(
            f"Bulk create {endpoint.name} (max 100, "
            + ("all or nothing)" if endpoint.bulk_atomic else "valid rows are kept)")
        ),
        name=f"bulk_create_{endpoint.name}",
    )




def _insert_all(engine, table, endpoint, payloads):  # type: ignore[no-untyped-def]
    """One transaction for every row; the first failure rolls all of them back."""
    current = -1
    try:
        with engine.begin() as conn:
            rows = []
            for current, payload in payloads:
                row = insert_returning(conn, table, payload, endpoint.fields, endpoint.primary_key)
                rows.append(_row_to_dict(row, endpoint.fields))
        return rows, None
    except IntegrityError as exc:
        err = conflict_error(exc)
        return [], {"index": current, "status": err.status, "detail": f"{err.detail} Nothing was saved."}
    except SQLAlchemyError as exc:
        err = db_error(exc)
        return [], {"index": current, "status": err.status, "detail": f"{err.detail} Nothing was saved."}


def _jsonable_row(payload: dict[str, Any]) -> dict[str, Any]:
    """Job payloads are stored as JSON: date-times as ISO text."""
    return {k: v.isoformat() if isinstance(v, (datetime, date)) else v for k, v in payload.items()}
