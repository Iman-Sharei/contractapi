"""Studio routes for saved specs: CRUD, OpenAPI export/diff, history, promote, client exports."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError

from contractapi.application.client_exports import compare_draft_with_saved
from contractapi.application.openapi_diff import diff_openapi
from contractapi.application.schema_drift import check_database_changes
from contractapi.application.studio_actions import (
    delete_api,
    promote_api,
    restore_version,
    save_api,
)
from contractapi.core.errors import AppError
from contractapi.infrastructure.db.errors import safe_db_message
from contractapi.infrastructure.persistence import spec_repo
from contractapi.infrastructure.security.auth import studio_actor
from contractapi.interfaces.http.studio.presenters import (
    _spec_json,
    _spec_yaml,
)
from contractapi.interfaces.http.studio.schemas import (
    DatabaseChangesResponse,
    DiffOpenApiRequest,
    OpenApiPreviewRequest,
    ProblemDetails,
    SaveSpecRequest,
    SpecDiffResponse,
)

# Included by studio.router under /studio with its auth dependency.
router = APIRouter()


@router.get("/specs")
def studio_list_specs() -> dict[str, Any]:
    return {"specs": spec_repo.list_specs()}


@router.post("/specs")
def studio_save_spec(body: SaveSpecRequest, request: Request) -> dict[str, Any]:
    spec = save_api(body.name, body.spec, actor=studio_actor(request))
    return {
        "saved": True,
        "name": body.name,
        "yaml": _spec_yaml(spec),
    }


@router.get("/specs/{name}")
def studio_get_spec(name: str) -> dict[str, Any]:
    spec = spec_repo.read_spec(name)
    return {
        "name": name,
        "spec": _spec_json(spec),
        "yaml": _spec_yaml(spec),
    }


@router.get(
    "/specs/{name}/database-changes",
    response_model=DatabaseChangesResponse,
    summary="Compare the saved API with its database now (removed/renamed columns, new columns)",
    responses={code: {"model": ProblemDetails} for code in (400, 401, 404)},
)
def studio_database_changes(name: str) -> dict[str, Any]:
    return check_database_changes(spec_repo.read_spec(name))


@router.post(
    "/specs/{name}/compare-draft",
    response_model=SpecDiffResponse,
    summary="What a draft would change for callers of the saved API (breaking changes)",
    responses={code: {"model": ProblemDetails} for code in (400, 401, 422)},
)
def studio_compare_draft(name: str, body: OpenApiPreviewRequest) -> dict[str, Any]:
    try:
        return compare_draft_with_saved(name, body.spec)
    except (SQLAlchemyError, ValueError) as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/database-unreachable",
            title="Cannot compare",
            status=400,
            detail=f"Could not build both versions to compare them: {safe_db_message(exc)}",
        ) from exc


@router.delete("/specs/{name}")
def studio_delete_spec(name: str, request: Request) -> dict[str, bool]:
    delete_api(name, actor=studio_actor(request))
    return {"deleted": True}


@router.get("/specs/{name}/openapi")
def studio_export_openapi(name: str) -> JSONResponse:
    spec = spec_repo.read_spec(name)
    try:
        doc = spec_repo.export_openapi_dict(spec, name)
    except Exception as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/database-unreachable",
            title="Cannot export OpenAPI",
            status=400,
            detail=f"The database must be reachable to export OpenAPI: {safe_db_message(exc)}",
        ) from exc
    return JSONResponse(doc)


@router.get("/specs/{name}/openapi.yaml", response_class=PlainTextResponse)
def studio_export_openapi_yaml(name: str) -> str:
    import yaml

    spec = spec_repo.read_spec(name)
    doc = spec_repo.export_openapi_dict(spec, name)
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


@router.get("/specs/{name}/history")
def studio_spec_history(name: str) -> dict[str, Any]:
    return {"name": name, "snapshots": spec_repo.list_snapshots(name)}


@router.get("/specs/{name}/history/{snapshot_id}")
def studio_spec_snapshot(name: str, snapshot_id: str) -> dict[str, Any]:
    spec = spec_repo.read_snapshot(name, snapshot_id)
    return {
        "name": name,
        "snapshot_id": snapshot_id,
        "spec": _spec_json(spec),
        "yaml": _spec_yaml(spec),
    }


@router.post("/specs/{name}/history/{snapshot_id}/restore")
def studio_restore_snapshot(name: str, snapshot_id: str, request: Request) -> dict[str, Any]:
    """Restore a historical snapshot over the current saved spec (snapshots again first)."""
    saved = restore_version(name, snapshot_id, actor=studio_actor(request))
    return {
        "restored": True,
        "name": name,
        "snapshot_id": snapshot_id,
        "yaml": _spec_yaml(saved),
    }


@router.post("/specs/{name}/promote")
def studio_promote(name: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    env = str(body.get("environment") or "staging")
    if env not in {"development", "staging", "production"}:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="environment must be development|staging|production",
        )
    result = promote_api(name, env, actor=studio_actor(request))
    return {
        "promoted": True,
        "environment": env,
        "name": result["name"],
        "database_kept": result["database_kept"],
        "yaml": _spec_yaml(result["spec"]),
    }


@router.get("/specs/{name}/postman")
def studio_postman(name: str) -> JSONResponse:
    from contractapi.application.client_exports import build_postman_collection

    spec = spec_repo.read_spec(name)
    return JSONResponse(build_postman_collection(spec, name))


@router.get("/specs/{name}/sdk.py", response_class=PlainTextResponse)
def studio_sdk_python(name: str) -> str:
    from contractapi.application.client_exports import build_python_sdk

    return build_python_sdk(spec_repo.read_spec(name), name)
