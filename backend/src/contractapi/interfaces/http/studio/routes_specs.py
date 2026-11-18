"""Studio routes for saved specs: CRUD, OpenAPI export/diff, history, promote, client exports."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from contractapi.application.openapi_diff import diff_openapi
from contractapi.core.errors import AppError
from contractapi.infrastructure.db.errors import safe_db_message
from contractapi.infrastructure.persistence import spec_repo
from contractapi.interfaces.http.studio.presenters import (
    _spec_json,
    _spec_yaml,
)
from contractapi.interfaces.http.studio.schemas import (
    DiffOpenApiRequest,
    SaveSpecRequest,
)

# Included by studio.router under /studio with its auth dependency.
router = APIRouter()


@router.get("/specs")
def studio_list_specs() -> dict[str, Any]:
    return {"specs": spec_repo.list_specs()}


@router.post("/specs")
def studio_save_spec(body: SaveSpecRequest) -> dict[str, Any]:
    spec = spec_repo.save_spec(body.name, body.spec)
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
def studio_restore_snapshot(name: str, snapshot_id: str) -> dict[str, Any]:
    """Restore a historical snapshot over the current saved spec (snapshots again first)."""
    snap = spec_repo.read_snapshot(name, snapshot_id)
    saved = spec_repo.save_spec(name, snap.model_dump(by_alias=True, mode="json"))
    return {
        "restored": True,
        "name": name,
        "snapshot_id": snapshot_id,
        "yaml": _spec_yaml(saved),
    }


@router.post("/specs/{name}/promote")
def studio_promote(name: str, body: dict[str, Any]) -> dict[str, Any]:
    env = str(body.get("environment") or "staging")
    if env not in {"development", "staging", "production"}:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="environment must be development|staging|production",
        )
    spec = spec_repo.promote_spec(name, environment=env)
    return {
        "promoted": True,
        "environment": env,
        "name": f"{name}_{env}" if not name.endswith(f"_{env}") else name,
        "yaml": _spec_yaml(spec),
    }


@router.get("/specs/{name}/postman")
def studio_postman(name: str) -> JSONResponse:
    from contractapi.application.postman_export import build_postman_collection

    spec = spec_repo.read_spec(name)
    return JSONResponse(build_postman_collection(spec))


@router.get("/specs/{name}/sdk.py", response_class=PlainTextResponse)
def studio_sdk_python(name: str) -> str:
    spec = spec_repo.read_spec(name)
    prefix = spec.app.api_prefix or ""
    lines = [
        "# Auto-generated thin client for contractapi — regenerate after contract changes",
        "from __future__ import annotations",
        "import os",
        "import httpx",
        "",
        "BASE = os.environ.get('CONTRACTAPI_BASE', 'http://127.0.0.1:8000/data')",
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
