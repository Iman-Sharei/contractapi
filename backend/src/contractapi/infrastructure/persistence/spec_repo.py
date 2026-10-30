"""Persist API specs as YAML files (git-friendly)."""

from __future__ import annotations

import re
from pathlib import Path

from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, dump_spec, load_spec, parse_spec

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def specs_dir() -> Path:
    path = Path(get_settings().specs_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-name",
            title="Invalid spec name",
            status=400,
            detail="Use lowercase letters, digits, _ or - (max 64).",
        )
    return name


def list_specs() -> list[dict[str, object]]:
    root = specs_dir()
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        if path.stem in seen:
            continue
        seen.add(path.stem)
        meta: dict[str, object] = {
            "name": path.stem,
            "path": str(path),
            "updated_at": path.stat().st_mtime,
            "title": path.stem,
            "version": "",
            "endpoint_count": 0,
            "auth": "",
            "api_prefix": "/v1",
            "read_only": True,
        }
        try:
            spec = load_spec(path)
            meta.update(
                {
                    "title": spec.app.title,
                    "version": spec.app.version,
                    "endpoint_count": len(spec.endpoints),
                    "auth": spec.app.auth.value,
                    "api_prefix": spec.app.api_prefix,
                    "read_only": spec.app.read_only,
                }
            )
        except Exception:
            pass
        items.append(meta)
    items.sort(key=lambda x: str(x["name"]))
    return items


def _history_dir(name: str) -> Path:
    path = specs_dir() / ".history" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_spec(name: str, raw: dict) -> ApiSpec:
    import time

    name = _safe_name(name)
    spec = parse_spec(raw)
    path = specs_dir() / f"{name}.yaml"
    # Snapshot previous version before overwrite
    if path.exists():
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        snap = _history_dir(name) / f"{stamp}.yaml"
        snap.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(dump_spec(spec), encoding="utf-8")
    return spec


def list_snapshots(name: str) -> list[dict[str, str]]:
    name = _safe_name(name)
    root = _history_dir(name)
    return [
        {"id": p.stem, "path": str(p)}
        for p in sorted(root.glob("*.yaml"), reverse=True)
    ]


def read_snapshot(name: str, snapshot_id: str) -> ApiSpec:
    name = _safe_name(name)
    path = _history_dir(name) / f"{snapshot_id}.yaml"
    if not path.exists():
        raise AppError(
            type_="https://contractapi.dev/problems/not-found",
            title="Snapshot not found",
            status=404,
            detail=f"No snapshot '{snapshot_id}' for '{name}'.",
        )
    return load_spec(path)


def promote_spec(name: str, *, environment: str) -> ApiSpec:
    """Copy spec and stamp app.environment (dev→staging→production workflow)."""
    spec = read_spec(name)
    data = spec.model_dump(by_alias=True, mode="json")
    data.setdefault("app", {})["environment"] = environment
    promoted_name = f"{name}_{environment}" if not name.endswith(f"_{environment}") else name
    return save_spec(promoted_name, data)


def read_spec(name: str) -> ApiSpec:
    name = _safe_name(name)
    path = specs_dir() / f"{name}.yaml"
    if not path.exists():
        alt = specs_dir() / f"{name}.yml"
        if alt.exists():
            path = alt
        else:
            raise AppError(
                type_="https://contractapi.dev/problems/not-found",
                title="Spec not found",
                status=404,
                detail=f"No saved spec named '{name}'.",
            )
    return load_spec(path)


def delete_spec(name: str) -> None:
    name = _safe_name(name)
    path = specs_dir() / f"{name}.yaml"
    alt = specs_dir() / f"{name}.yml"
    target = path if path.exists() else alt
    if not target.exists():
        raise AppError(
            type_="https://contractapi.dev/problems/not-found",
            title="Spec not found",
            status=404,
            detail=f"No saved spec named '{name}'.",
        )
    target.unlink()


def export_openapi_dict(spec: ApiSpec) -> dict:
    from fastapi.openapi.utils import get_openapi

    from contractapi.application.data_api_builder import create_data_app

    app = create_data_app(spec)
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
