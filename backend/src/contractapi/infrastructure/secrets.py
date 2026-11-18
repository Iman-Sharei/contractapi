"""Server-side secret store + `${secret:NAME}` / `${env:NAME}` references in specs.

Specs are YAML meant for git, so they must never hold a database password. Studio moves
a literal password into `SPECS_DIR/.secrets/<name>` (0600) and writes a reference instead.
DevOps can use `${env:VAR}` to read from the environment.

ponytail: plaintext files protected by filesystem permissions. Ceiling: anyone with
read access to SPECS_DIR as the service user can read them; upgrade path is a KMS /
Vault backend behind put_secret/get_secret.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from contractapi.core.config import get_settings
from contractapi.core.errors import AppError

_REF = re.compile(r"\$\{(secret|env):([A-Za-z0-9_.-]{1,64})\}")
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
# scheme://user:PASSWORD@host… (password may be empty or a reference)
_URL_PASSWORD = re.compile(r"^(?P<head>[A-Za-z0-9+.-]+://[^:/@]+:)(?P<pw>[^@]*)(?P<tail>@.*)$")
MASK = "****"


def _store_dir() -> Path:
    root = Path(get_settings().specs_dir).expanduser().resolve() / ".secrets"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _check_name(name: str) -> str:
    if not _NAME.match(name) or name.startswith("."):
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-name",
            title="Invalid secret name",
            status=400,
            detail="Secret names use letters, digits, '.', '_' or '-' (max 64).",
        )
    return name


def put_secret(name: str, value: str) -> str:
    """Store a secret and return its `${secret:NAME}` reference."""
    path = _store_dir() / _check_name(name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(value)
    os.chmod(path, 0o600)
    return f"${{secret:{name}}}"


def get_secret(name: str) -> str | None:
    path = _store_dir() / _check_name(name)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def resolve_refs(text: str) -> str:
    """Replace ${secret:NAME} / ${env:NAME}; a missing value is a clear configuration error."""

    def sub(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2)
        value = get_secret(name) if kind == "secret" else os.environ.get(name)
        if value is None:
            where = "Studio secret store" if kind == "secret" else "environment"
            raise AppError(
                type_="https://contractapi.dev/problems/misconfigured",
                title="Missing secret",
                status=500,
                detail=f"'{name}' is referenced by the spec but not found in the {where}. "
                "Re-enter the database password in Studio and save.",
            )
        return value

    return _REF.sub(sub, text) if text and "${" in text else text


def has_literal_password(url: str) -> bool:
    m = _URL_PASSWORD.match(url or "")
    return bool(m and m.group("pw") and not _REF.fullmatch(m.group("pw")))


def mask_url(url: str) -> str:
    """Hide a literal password for display; references are already safe to show."""
    if not has_literal_password(url):
        return url
    m = _URL_PASSWORD.match(url)
    assert m is not None
    return f"{m.group('head')}{MASK}{m.group('tail')}"


def secure_database_url(url: str, secret_name: str) -> str:
    """Move a literal password into the secret store; return the URL with a reference.

    A masked password (`****`, from a Studio round-trip) re-uses the existing secret.
    """
    m = _URL_PASSWORD.match(url or "")
    if not m or not m.group("pw") or _REF.fullmatch(m.group("pw")):
        return url
    name = _check_name(secret_name)
    if m.group("pw") == MASK:
        if get_secret(name) is None:
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Password required",
                status=422,
                detail="The database password is hidden (****). Re-enter it before saving.",
            )
        return f"{m.group('head')}${{secret:{name}}}{m.group('tail')}"
    return f"{m.group('head')}{put_secret(name, m.group('pw'))}{m.group('tail')}"


def secure_spec_payload(raw: dict, spec_name: str) -> dict:
    """Return a copy of a raw spec dict with literal secrets moved into the store."""
    import copy

    out = copy.deepcopy(raw)
    db = out.get("database")
    if isinstance(db, dict) and isinstance(db.get("url"), str):
        db["url"] = secure_database_url(db["url"], f"db-{spec_name}")
    hooks = (out.get("app") or {}).get("webhooks") or []
    for i, hook in enumerate(hooks):
        secret = hook.get("secret") if isinstance(hook, dict) else None
        if not secret or _REF.fullmatch(secret):
            continue
        name = f"webhook-{spec_name}-{i}"
        if secret == MASK:
            if get_secret(name) is None:
                raise AppError(
                    type_="https://contractapi.dev/problems/validation-error",
                    title="Secret required",
                    status=422,
                    detail=f"Webhook #{i + 1} secret is hidden (****). Re-enter it before saving.",
                )
            hook["secret"] = f"${{secret:{name}}}"
        else:
            hook["secret"] = put_secret(name, secret)
    return out


def mask_spec_dict(data: dict) -> dict:
    """Copy of a dumped spec safe to return to clients (no literal passwords/secrets)."""
    import copy

    out = copy.deepcopy(data)
    db = out.get("database")
    if isinstance(db, dict) and isinstance(db.get("url"), str):
        db["url"] = mask_url(db["url"])
    for hook in (out.get("app") or {}).get("webhooks") or []:
        if isinstance(hook, dict) and hook.get("secret") and not _REF.fullmatch(hook["secret"]):
            hook["secret"] = MASK
    return out
