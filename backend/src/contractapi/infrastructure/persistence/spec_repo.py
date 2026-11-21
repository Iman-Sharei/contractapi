"""Persist API specs as YAML files (git-friendly)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

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
        except (ValueError, OSError, yaml.YAMLError):
            meta["invalid"] = True  # listed so the user can open and fix it
        items.append(meta)
    items.sort(key=lambda x: str(x["name"]))
    return items


def _history_dir(name: str) -> Path:
    path = specs_dir() / ".history" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_spec(name: str, raw: dict) -> ApiSpec:
    import time

    from contractapi.infrastructure.secrets import secure_spec_payload

    name = _safe_name(name)
    # Never write a literal password to (git-friendly) YAML: move it to the secret store.
    try:
        spec = parse_spec(secure_spec_payload(raw, name))
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(x) for x in e.get('loc', ()))}: {str(e.get('msg', '')).removeprefix('Value error, ')}"
            for e in exc.errors()
        ]
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-spec",
            title="Invalid specification",
            status=400,
            detail=errors[0] if len(errors) == 1 else "The API file has problems: " + "; ".join(errors),
            extensions={"errors": errors},
        ) from exc
    path = specs_dir() / f"{name}.yaml"
    # Snapshot previous version before overwrite
    if path.exists():
        # Microsecond suffix: two saves in the same second must not overwrite a snapshot.
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{time.time_ns() // 1000 % 1_000_000:06d}"
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


def spec_exists(name: str) -> bool:
    name = _safe_name(name)
    return (specs_dir() / f"{name}.yaml").exists() or (specs_dir() / f"{name}.yml").exists()


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


def export_openapi_dict(spec: ApiSpec, name: str | None = None) -> dict:
    """Complete OpenAPI of a spec (kept for the CLI and older imports)."""
    from contractapi.application.client_exports import export_openapi

    return export_openapi(spec, name)
