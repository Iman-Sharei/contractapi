"""POST /{path}/{id}/restore: bring back a soft-deleted row (spec `soft_delete.restore`)."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from contractapi.application.data_api.common import (
    _audit,
    _bind_path_type,
    _etag_for,
    _invalidate_endpoint_cache,
    _json_response,
    _project_fields,
    _python_type,
    _row_to_dict,
    _visible_fields,
)
from contractapi.application.data_api.write_rules import db_timezone, now_for
from contractapi.application.data_api.write_support import conflict_error
from contractapi.application.row_security import row_level_clause
from contractapi.core.errors import AppError
from contractapi.infrastructure.db.errors import db_error
from contractapi.infrastructure.webhooks import dispatch_webhooks


def _add_restore(router, engine, table, endpoint, spec, tags) -> None:  # type: ignore[no-untyped-def]
    pk = endpoint.primary_key
    deleted = table.c[endpoint.soft_delete.column]
    tz = db_timezone(spec)

    def restore_item(request: Request, item_id: Any) -> Any:
        visible = _visible_fields(spec, endpoint, request)  # role gate before any side effect
        scope = [table.c[pk] == item_id]
        owner = row_level_clause(table, endpoint, request)
        if owner is not None:
            scope.append(owner)  # only your own rows, as for every other write
        values: dict[str, Any] = {deleted.name: None}
        if endpoint.timestamps and endpoint.timestamps.updated_at:
            values[endpoint.timestamps.updated_at] = now_for(table, endpoint.timestamps.updated_at, tz)
        try:
            with engine.begin() as conn:
                changed = conn.execute(
                    table.update().where(and_(*scope, deleted.isnot(None))).values(**values)
                ).rowcount
                row = conn.execute(
                    select(*(table.c[f] for f in endpoint.fields)).where(and_(*scope))
                ).fetchone()
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
        if changed:  # restoring a row that is not deleted is a no-op (safe to retry)
            _invalidate_endpoint_cache(spec, endpoint)
            _audit(spec, "restore", endpoint, request, status=200, resource_id=item_id)
            dispatch_webhooks(spec, event="update", endpoint=endpoint.name, payload=result)
        return _json_response(_project_fields(result, visible, []), headers={"ETag": _etag_for(result, endpoint)})

    restore_item.__name__ = f"restore_{endpoint.name}"
    _bind_path_type(restore_item, "item_id", _python_type(table.c[pk].type))
    router.add_api_route(
        f"{endpoint.path}/{{item_id}}/restore",
        restore_item,
        methods=["POST"],
        tags=tags,
        summary=f"Restore a deleted {endpoint.name}",
        name=f"restore_{endpoint.name}",
    )


__all__ = ["_add_restore"]
