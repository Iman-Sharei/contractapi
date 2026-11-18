"""Studio control-plane HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.openapi.utils import get_openapi
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError

from contractapi.application.data_api_builder import create_data_app
from contractapi.application.studio_service import (
    activate_spec,
    introspect,
    spec_store,
    validate_spec_payload,
)
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import parse_spec
from contractapi.infrastructure.db.errors import safe_db_message
from contractapi.infrastructure.security.auth import require_studio_api_key
from contractapi.interfaces.http.studio.presenters import (
    _spec_json,
    _spec_yaml,
)
from contractapi.interfaces.http.studio.schemas import (
    DumpYamlRequest,
    IntrospectRequest,
    OpenApiPreviewRequest,
    ServeInfoResponse,
    SqlPreviewRequest,
    ValidateSpecRequest,
    ValidateSpecResponse,
)

router = APIRouter(
    prefix="/studio",
    tags=["studio"],
    dependencies=[Depends(require_studio_api_key)],
)


@router.get("/health")
def studio_health() -> dict[str, Any]:
    from contractapi.application.graphql_facade import graphql_available
    from contractapi.core.config import get_settings
    from contractapi.infrastructure.security.oidc import oidc_browser_enabled, oidc_enabled

    settings = get_settings()
    return {
        "status": "ok",
        "plane": "studio",
        "oidc": oidc_enabled(settings),
        "oidc_browser": oidc_browser_enabled(settings),
        "job_queue": bool(settings.job_queue_enabled and settings.redis_url),
        "multi_active": True,
        "graphql": graphql_available(),
        "active_apis": len(spec_store.all()),
        "experimental": sorted(settings.experimental_set),
    }


@router.post("/introspect")
def studio_introspect(body: IntrospectRequest) -> dict[str, Any]:
    tables = introspect(body.database_url, schema=body.schema_name)
    return {"schema": body.schema_name, "tables": tables, "count": len(tables)}


@router.post("/validate", response_model=ValidateSpecResponse)
def studio_validate(body: ValidateSpecRequest) -> ValidateSpecResponse:
    result = validate_spec_payload(body.spec, check_db=body.check_db)
    return ValidateSpecResponse(**result)


@router.post("/activate", response_model=ServeInfoResponse)
def studio_activate(body: ValidateSpecRequest) -> ServeInfoResponse:
    key = body.name or "_default"
    activate_spec(body.spec, name=key, primary=True)
    return ServeInfoResponse(
        message=(
            f"Data API '{key}' activated under /data (primary) and /apis/{key}. "
            "Open /data/docs for Swagger."
        ),
        name=key,
        mount=f"/apis/{key}",
        primary=True,
    )


@router.post("/activate/{name}", response_model=ServeInfoResponse)
def studio_activate_named(name: str, body: ValidateSpecRequest, primary: bool = False) -> ServeInfoResponse:
    """Activate an additional named API without replacing /data unless primary=true."""
    activate_spec(body.spec, name=name, primary=primary)
    return ServeInfoResponse(
        message=f"Data API '{name}' activated under /apis/{name}"
        + (" and set as /data primary." if primary else "."),
        name=name,
        mount=f"/apis/{name}",
        primary=primary,
    )


@router.get("/active")
def studio_active() -> dict[str, Any]:
    spec = spec_store.active
    if spec is None:
        return {"active": False, "spec": None, "yaml": None, "name": None, "apis": []}
    return {
        "active": True,
        "name": spec_store.active_name,
        "spec": _spec_json(spec),
        "yaml": _spec_yaml(spec),
        "apis": sorted(spec_store.all()),
        "summary": {
            "title": spec.app.title,
            "version": spec.app.version,
            "endpoint_count": len(spec.endpoints),
            "auth": spec.app.auth.value,
            "api_prefix": spec.app.api_prefix,
            "read_only": spec.app.read_only,
            "endpoints": [
                {"name": e.name, "path": e.path, "methods": [m.value for m in e.methods]}
                for e in spec.endpoints
            ],
        },
    }


@router.get("/active/list")
def studio_active_list() -> dict[str, Any]:
    items = []
    for name, spec in spec_store.all().items():
        items.append(
            {
                "name": name,
                "primary": name == spec_store.active_name,
                "title": spec.app.title,
                "version": spec.app.version,
                "endpoint_count": len(spec.endpoints),
                "mount": f"/apis/{name}",
                "primary_mount": "/data" if name == spec_store.active_name else None,
            }
        )
    return {"count": len(items), "apis": items}


@router.post("/deactivate")
def studio_deactivate(name: str | None = None) -> dict[str, Any]:
    if name:
        spec_store.remove(name)
        return {
            "active": spec_store.active is not None,
            "message": f"API '{name}' deactivated.",
            "apis": sorted(spec_store.all()),
        }
    spec_store.clear()
    return {"active": False, "message": "All data APIs deactivated.", "apis": []}


@router.post("/preview-openapi")
def studio_preview_openapi(body: OpenApiPreviewRequest) -> dict[str, Any]:
    result = validate_spec_payload(body.spec, check_db=False)
    if not result["valid"]:
        return {"valid": False, "errors": result["errors"], "openapi": None}
    try:
        spec = parse_spec(body.spec)
        app = create_data_app(spec)
        openapi = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        return {"valid": True, "errors": [], "openapi": openapi}
    except (SQLAlchemyError, AppError, ValueError, RuntimeError) as exc:
        # Building the app reflects the DB; when it is unreachable the preview waits.
        return {
            "valid": True,
            "errors": [],
            "warnings": [f"OpenAPI preview deferred until DB is reachable: {safe_db_message(exc)}"],
            "openapi": None,
        }


@router.post("/sql-preview")
def studio_sql_preview(body: SqlPreviewRequest) -> dict[str, Any]:
    """Discover output columns for a custom SELECT (Studio SQL endpoints)."""
    from contractapi.application.sql_endpoint import preview_sql_columns
    from contractapi.domain.models.spec import DatabaseConfig, DatabaseDriver
    from contractapi.infrastructure.db.engine import create_engine_for_config

    try:
        try:
            drv = DatabaseDriver(body.driver)
        except ValueError:
            drv = DatabaseDriver.POSTGRES
        engine = create_engine_for_config(
            DatabaseConfig(url=body.database_url, driver=drv),
            pooled=False,
        )
        columns = preview_sql_columns(engine, body.sql)
    except Exception as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/sql-preview-failed",
            title="SQL preview failed",
            status=400,
            detail=safe_db_message(exc),
        ) from exc
    return {"columns": columns, "count": len(columns)}


@router.post("/dump-yaml", response_class=PlainTextResponse)
def studio_dump_yaml(body: DumpYamlRequest) -> str:
    """Canonical YAML dump from a draft spec (full contract)."""
    try:
        spec = parse_spec(body.spec)
    except Exception as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-spec",
            title="Invalid specification",
            status=400,
            detail=str(exc),
        ) from exc
    return _spec_yaml(spec)


# Route groups (registered on the same /studio router, so they share its auth dependency).
from contractapi.interfaces.http.studio import routes_ops, routes_specs, routes_tools

router.include_router(routes_tools.router)
router.include_router(routes_specs.router)
router.include_router(routes_ops.router)
