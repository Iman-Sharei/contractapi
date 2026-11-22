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


def create_api_key(
    name: str,
    *,
    apis: list[str] | None,
    access: str | None,
    expires_in_days: int | None = None,
    scopes: list[str] | None = None,
    actor: dict[str, Any] | None,
) -> dict[str, Any]:
    """A key for the named saved APIs ("*" = every API), read or read & write, optionally expiring."""
    import time

    from contractapi.core.errors import AppError

    if apis is None and scopes is None:
        apis = []  # new callers must say which APIs (least privilege); see below
    chosen = sorted(set(apis if apis is not None else [api_keys.ALL_APIS]))
    if not chosen:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="Choose at least one API this key may call (or all APIs).",
        )
    unknown = [a for a in chosen if a != api_keys.ALL_APIS and not spec_repo.spec_exists(a)]
    if unknown:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail=f"No saved API named {', '.join(repr(u) for u in unknown)}. Check the name in My APIs.",
        )
    expires_at = time.time() + expires_in_days * 86_400 if expires_in_days else None
    created = api_keys.create_key(name=name, apis=chosen, access=access, expires_at=expires_at, scopes=scopes)
    _log("studio.key.create", actor, id=created["id"], name=name, prefix=created["prefix"],
         apis=created["apis"], access=created["access"], expires_at=expires_at)
    return created


def revoke_api_key(key_id: str, *, actor: dict[str, Any] | None) -> bool:
    ok = api_keys.revoke_key(key_id)
    if ok:
        _log("studio.key.revoke", actor, id=key_id)
    return ok


def record_token_issued(api: str | None, subject: str, *, actor: dict[str, Any] | None) -> None:
    _log("studio.token.issue", actor, api=api, subject=subject)


def test_company_login(issuer: str, jwks_url: str | None) -> dict[str, Any]:
    """Studio's "Test connection": can this server read the login server's signing keys?"""
    from pydantic import ValidationError

    from contractapi.core.errors import AppError
    from contractapi.domain.models.options import JwtConfig
    from contractapi.infrastructure.security.idp import (
        LoginServerUnreachable,
        describe_login_server,
    )

    try:
        cfg = JwtConfig(provider="oidc", issuer=issuer, audience="check", jwks_url=jwks_url or None)
    except ValidationError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail=str(exc.errors()[0].get("msg", "")).removeprefix("Value error, "),
        ) from exc
    try:
        return describe_login_server(cfg.issuer, cfg.jwks_url)
    except LoginServerUnreachable as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/auth-unavailable",
            title="Login server unreachable",
            status=400,
            detail=f"Could not read the login server's signing keys ({exc}). Check the address, and "
            "that this server can reach it.",
        ) from exc
