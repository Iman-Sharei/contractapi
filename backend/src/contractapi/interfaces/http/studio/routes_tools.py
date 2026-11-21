"""Studio tool routes: dbt import and read-only git browser."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from contractapi.core.errors import AppError

# Included by studio.router under /studio with its auth dependency.
router = APIRouter()


@router.post("/import/dbt")
def studio_import_dbt(body: dict[str, Any]) -> dict[str, Any]:
    """Convert a dbt schema.yml (YAML or JSON text) or manifest.json into endpoint drafts."""
    from contractapi.application.dbt_import import import_dbt_payload, import_dbt_text

    if isinstance(body.get("text"), str):
        return import_dbt_text(body["text"])
    payload = body.get("manifest") if "manifest" in body else body.get("schema") or body
    if payload is None:
        raise AppError(
            type_="https://contractapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="Paste the contents of a dbt schema.yml or manifest.json.",
        )
    return import_dbt_payload(payload)


@router.get("/git/status")
def studio_git_status() -> dict[str, Any]:
    from contractapi.application.git_browser import GitBrowserError, git_status

    try:
        return git_status()
    except GitBrowserError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/git-error",
            title="Git error",
            status=400,
            detail=str(exc),
        ) from exc


@router.get("/git/branches")
def studio_git_branches() -> dict[str, Any]:
    from contractapi.application.git_browser import GitBrowserError, list_branches

    try:
        return list_branches()
    except GitBrowserError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/git-error",
            title="Git error",
            status=400,
            detail=str(exc),
        ) from exc


@router.get("/git/tree")
def studio_git_tree(ref: str = "HEAD", path: str = "") -> dict[str, Any]:
    from contractapi.application.git_browser import GitBrowserError, list_tree

    try:
        return list_tree(ref=ref, path=path)
    except GitBrowserError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/git-error",
            title="Git error",
            status=400,
            detail=str(exc),
        ) from exc


@router.get("/git/file")
def studio_git_file(path: str, ref: str = "HEAD") -> dict[str, Any]:
    from contractapi.application.git_browser import GitBrowserError, read_file

    try:
        return read_file(ref=ref, path=path)
    except GitBrowserError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/git-error",
            title="Git error",
            status=400,
            detail=str(exc),
        ) from exc
