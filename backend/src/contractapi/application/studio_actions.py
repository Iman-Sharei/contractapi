"""Studio control-plane actions that change something, each recorded in the audit trail.

Routes parse input and call one of these with the acting Studio user (see audit-logging rule:
activate/deactivate/save/delete/restore/promote, key issue/revoke, token issue are always logged).
Meta holds names and ids only: never spec bodies, keys, tokens or passwords.
"""

from __future__ import annotations

from typing import Any

from contractapi.application.studio_service import activate_spec, spec_store
from contractapi.domain.models.spec import ApiSpec
from contractapi.infrastructure import api_keys
from contractapi.infrastructure.audit import audit_event
from contractapi.infrastructure.persistence import spec_repo


def _log(action: str, actor: dict[str, Any] | None, **meta: Any) -> None:
    audit_event(action=action, principal=actor, status=200, meta=meta)


def activate_api(raw: dict[str, Any], *, name: str, primary: bool, actor: dict[str, Any] | None) -> ApiSpec:
    spec = activate_spec(raw, name=name, primary=primary)
    _log("studio.spec.activate", actor, name=name, primary=primary, endpoints=len(spec.endpoints))
    return spec


def deactivate_api(name: str | None, *, actor: dict[str, Any] | None) -> None:
    if name:
        spec_store.remove(name)
    else:
        spec_store.clear()
    _log("studio.spec.deactivate", actor, name=name or "*")


def save_api(name: str, raw: dict[str, Any], *, actor: dict[str, Any] | None) -> ApiSpec:
    spec = spec_repo.save_spec(name, raw)
    _log("studio.spec.save", actor, name=name, endpoints=len(spec.endpoints))
    return spec


def delete_api(name: str, *, actor: dict[str, Any] | None) -> None:
    spec_repo.delete_spec(name)
    _log("studio.spec.delete", actor, name=name)


def restore_version(name: str, snapshot_id: str, *, actor: dict[str, Any] | None) -> ApiSpec:
    snap = spec_repo.read_snapshot(name, snapshot_id)
    spec = spec_repo.save_spec(name, snap.model_dump(by_alias=True, mode="json"))
    _log("studio.spec.restore", actor, name=name, snapshot_id=snapshot_id)
    return spec


def promote_api(name: str, environment: str, *, actor: dict[str, Any] | None) -> dict[str, Any]:
    """Copy an API to another environment. An existing copy keeps its own database (staging
    and production read their own data); a first copy starts on the same database and the
    answer says so, so the user can point it elsewhere."""
    source = spec_repo.read_spec(name)
    target = name if name.endswith(f"_{environment}") else f"{name}_{environment}"
    data = source.model_dump(by_alias=True, mode="json")
    data.setdefault("app", {})["environment"] = environment
    existing = spec_repo.read_spec(target) if target != name and spec_repo.spec_exists(target) else None
    if existing is not None:
        data["database"] = existing.model_dump(by_alias=True, mode="json")["database"]
    spec = spec_repo.save_spec(target, data)
    _log("studio.spec.promote", actor, name=name, target=target, environment=environment,
         database_kept=existing is not None)
    return {"name": target, "spec": spec, "database_kept": existing is not None}


def create_api_key(name: str, scopes: list[str], *, actor: dict[str, Any] | None) -> dict[str, Any]:
    created = api_keys.create_key(name=name, scopes=scopes)
    _log("studio.key.create", actor, id=created["id"], name=name, prefix=created["prefix"])
    return created


def revoke_api_key(key_id: str, *, actor: dict[str, Any] | None) -> bool:
    ok = api_keys.revoke_key(key_id)
    if ok:
        _log("studio.key.revoke", actor, id=key_id)
    return ok


def record_token_issued(api: str | None, subject: str, *, actor: dict[str, Any] | None) -> None:
    _log("studio.token.issue", actor, api=api, subject=subject)
