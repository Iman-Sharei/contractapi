"""Studio control-plane HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, PlainTextResponse

from dataapi.application.data_api_builder import create_data_app
from dataapi.application.openapi_diff import diff_openapi
from dataapi.application.studio_service import (
    activate_spec,
    introspect,
    spec_store,
    validate_spec_payload,
)
from dataapi.core.errors import AppError
from dataapi.domain.models.spec import dump_spec, parse_spec
from dataapi.infrastructure.persistence import spec_repo
from dataapi.infrastructure.security.auth import require_studio_api_key
from dataapi.infrastructure.security.jwt_tokens import issue_token
from dataapi.interfaces.http.studio.schemas import (
    DiffOpenApiRequest,
    DumpYamlRequest,
    IntrospectRequest,
    IssueTokenRequest,
    OpenApiPreviewRequest,
    SaveSpecRequest,
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
def studio_health() -> dict[str, str]:
    return {"status": "ok", "plane": "studio"}


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
    )


@router.post("/activate/{name}", response_model=ServeInfoResponse)
def studio_activate_named(name: str, body: ValidateSpecRequest, primary: bool = False) -> ServeInfoResponse:
    """Activate an additional named API without replacing /data unless primary=true."""
    activate_spec(body.spec, name=name, primary=primary)
    return ServeInfoResponse(
        message=f"Data API '{name}' activated under /apis/{name}"
        + (" and set as /data primary." if primary else "."),
    )


@router.get("/active")
def studio_active() -> dict[str, Any]:
    spec = spec_store.active
    if spec is None:
        return {"active": False, "spec": None, "yaml": None, "name": None, "apis": []}
    return {
        "active": True,
        "name": spec_store.active_name,
        "spec": spec.model_dump(by_alias=True, mode="json"),
        "yaml": dump_spec(spec),
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
    except Exception as exc:
        return {
            "valid": True,
            "errors": [],
            "warnings": [f"OpenAPI preview deferred until DB is reachable: {exc}"],
            "openapi": None,
        }


@router.get("/specs")
def studio_list_specs() -> dict[str, Any]:
    return {"specs": spec_repo.list_specs()}


@router.post("/specs")
def studio_save_spec(body: SaveSpecRequest) -> dict[str, Any]:
    spec = spec_repo.save_spec(body.name, body.spec)
    return {
        "saved": True,
        "name": body.name,
        "yaml": dump_spec(spec),
    }


@router.get("/specs/{name}")
def studio_get_spec(name: str) -> dict[str, Any]:
    spec = spec_repo.read_spec(name)
    return {
        "name": name,
        "spec": spec.model_dump(by_alias=True, mode="json"),
        "yaml": dump_spec(spec),
    }


@router.delete("/specs/{name}")
def studio_delete_spec(name: str) -> dict[str, bool]:
    spec_repo.delete_spec(name)
    return {"deleted": True}


@router.get("/specs/{name}/openapi")
def studio_export_openapi(name: str) -> JSONResponse:
    spec = spec_repo.read_spec(name)
    try:
        doc = spec_repo.export_openapi_dict(spec)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Cannot export OpenAPI (is DB reachable?): {exc}"},
        )
    return JSONResponse(doc)


@router.get("/specs/{name}/openapi.yaml", response_class=PlainTextResponse)
def studio_export_openapi_yaml(name: str) -> str:
    import yaml

    spec = spec_repo.read_spec(name)
    doc = spec_repo.export_openapi_dict(spec)
    return yaml.safe_dump(doc, sort_keys=False)


@router.post("/openapi/diff")
def studio_openapi_diff(body: DiffOpenApiRequest) -> dict[str, Any]:
    """Diff two OpenAPI docs — compatible with swagger-diff-ui style consumers."""
    return diff_openapi(body.before, body.after)


@router.post("/openapi/diff-specs")
def studio_diff_saved_specs(before: str, after: str) -> dict[str, Any]:
    before_spec = spec_repo.read_spec(before)
    after_spec = spec_repo.read_spec(after)
    before_doc = spec_repo.export_openapi_dict(before_spec)
    after_doc = spec_repo.export_openapi_dict(after_spec)
    return diff_openapi(before_doc, after_doc)


@router.post("/token")
def studio_issue_token(body: IssueTokenRequest) -> dict[str, str]:
    """Mint a JWT for testing data-plane auth=jwt."""
    from dataapi.domain.models.spec import JwtConfig

    token = issue_token(
        subject=body.sub,
        roles=body.roles,
        jwt_cfg=JwtConfig(),
        expires_minutes=body.expires_minutes,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/sql-preview")
def studio_sql_preview(body: SqlPreviewRequest) -> dict[str, Any]:
    """Discover output columns for a custom SELECT (Studio SQL endpoints)."""
    from dataapi.application.sql_endpoint import preview_sql_columns
    from dataapi.infrastructure.db.engine import create_pg_engine

    try:
        engine = create_pg_engine(body.database_url, pooled=False)
        columns = preview_sql_columns(engine, body.sql)
    except Exception as exc:
        raise AppError(
            type_="https://dataapi.dev/problems/sql-preview-failed",
            title="SQL preview failed",
            status=400,
            detail=str(exc),
        ) from exc
    return {"columns": columns, "count": len(columns)}


@router.post("/dump-yaml", response_class=PlainTextResponse)
def studio_dump_yaml(body: DumpYamlRequest) -> str:
    """Canonical YAML dump from a draft spec (full contract)."""
    try:
        spec = parse_spec(body.spec)
    except Exception as exc:
        raise AppError(
            type_="https://dataapi.dev/problems/invalid-spec",
            title="Invalid specification",
            status=400,
            detail=str(exc),
        ) from exc
    return dump_spec(spec)


@router.get("/keys")
def studio_list_keys() -> dict[str, Any]:
    from dataapi.infrastructure.api_keys import list_keys

    return {"keys": list_keys()}


@router.post("/keys")
def studio_create_key(body: dict[str, Any]) -> dict[str, Any]:
    from dataapi.infrastructure.api_keys import create_key

    name = str(body.get("name") or "default")
    scopes = list(body.get("scopes") or ["*"])
    return create_key(name=name, scopes=scopes)


@router.delete("/keys/{key_id}")
def studio_revoke_key(key_id: str) -> dict[str, bool]:
    from dataapi.infrastructure.api_keys import revoke_key

    ok = revoke_key(key_id)
    if not ok:
        raise AppError(
            type_="https://dataapi.dev/problems/not-found",
            title="Not Found",
            status=404,
            detail=f"Key {key_id} not found or already revoked",
        )
    return {"revoked": True}


@router.get("/audit")
def studio_audit(limit: int = 100) -> dict[str, Any]:
    from dataapi.infrastructure.audit import recent_events

    return {"events": recent_events(limit=min(max(limit, 1), 500))}


@router.get("/specs/{name}/history")
def studio_spec_history(name: str) -> dict[str, Any]:
    return {"name": name, "snapshots": spec_repo.list_snapshots(name)}


@router.get("/specs/{name}/history/{snapshot_id}")
def studio_spec_snapshot(name: str, snapshot_id: str) -> dict[str, Any]:
    spec = spec_repo.read_snapshot(name, snapshot_id)
    return {
        "name": name,
        "snapshot_id": snapshot_id,
        "spec": spec.model_dump(by_alias=True, mode="json"),
        "yaml": dump_spec(spec),
    }


@router.post("/specs/{name}/history/{snapshot_id}/restore")
def studio_restore_snapshot(name: str, snapshot_id: str) -> dict[str, Any]:
    """Restore a historical snapshot over the current saved spec (snapshots again first)."""
    snap = spec_repo.read_snapshot(name, snapshot_id)
    saved = spec_repo.save_spec(name, snap.model_dump(by_alias=True, mode="json"))
    return {
        "restored": True,
        "name": name,
        "snapshot_id": snapshot_id,
        "yaml": dump_spec(saved),
    }


@router.post("/specs/{name}/promote")
def studio_promote(name: str, body: dict[str, Any]) -> dict[str, Any]:
    env = str(body.get("environment") or "staging")
    if env not in {"development", "staging", "production"}:
        raise AppError(
            type_="https://dataapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="environment must be development|staging|production",
        )
    spec = spec_repo.promote_spec(name, environment=env)
    return {
        "promoted": True,
        "environment": env,
        "name": f"{name}_{env}" if not name.endswith(f"_{env}") else name,
        "yaml": dump_spec(spec),
    }


@router.get("/specs/{name}/postman")
def studio_postman(name: str) -> JSONResponse:
    from dataapi.application.postman_export import build_postman_collection

    spec = spec_repo.read_spec(name)
    return JSONResponse(build_postman_collection(spec))


@router.get("/specs/{name}/sdk.py", response_class=PlainTextResponse)
def studio_sdk_python(name: str) -> str:
    spec = spec_repo.read_spec(name)
    prefix = spec.app.api_prefix or ""
    lines = [
        "# Auto-generated thin client for dataapi — regenerate after contract changes",
        "from __future__ import annotations",
        "import os",
        "import httpx",
        "",
        "BASE = os.environ.get('DATAAPI_BASE', 'http://127.0.0.1:8000/data')",
        "API_KEY = os.environ.get('DATA_API_KEY', '')",
        "",
        "def _headers():",
        "    h = {'Accept': 'application/json'}",
        "    if API_KEY:",
        "        h['X-API-Key'] = API_KEY",
        "    return h",
        "",
    ]
    for ep in spec.endpoints:
        fn = ep.name
        path = f"{prefix}{ep.path}"
        lines.append(f"def list_{fn}(**params):")
        lines.append(f"    r = httpx.get(f'{{BASE}}{path}', params=params, headers=_headers())")
        lines.append("    r.raise_for_status()")
        lines.append("    return r.json()")
        lines.append("")
        lines.append(f"def get_{fn}(item_id, **params):")
        lines.append(
            f"    r = httpx.get(f'{{BASE}}{path}/{{item_id}}', params=params, headers=_headers())"
        )
        lines.append("    r.raise_for_status()")
        lines.append("    return r.json()")
        lines.append("")
    return "\n".join(lines)

