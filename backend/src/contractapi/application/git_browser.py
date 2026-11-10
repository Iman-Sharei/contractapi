"""Read-only git helpers for Studio (branch / file browser)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class GitBrowserError(RuntimeError):
    pass


def _run(repo: Path, *args: str, timeout: float = 8.0) -> str:
    import os

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Compose mounts host checkout as another UID → mark safe for read-only browse.
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "safe.directory"
    env["GIT_CONFIG_VALUE_0"] = "*"
    try:
        proc = subprocess.run(  # noqa: S603
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise GitBrowserError("git executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitBrowserError("git command timed out") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git failed").strip()
        raise GitBrowserError(detail[:500])
    return proc.stdout


def resolve_repo(path: str | None = None) -> Path:
    import os

    candidate = path or os.environ.get("GIT_REPO_PATH") or "."
    root = Path(candidate).expanduser().resolve()
    if not root.exists():
        raise GitBrowserError(f"Path not found: {root}")
    probe = root if root.is_dir() else root.parent
    try:
        out = _run(probe, "rev-parse", "--show-toplevel")
    except GitBrowserError:
        raise GitBrowserError(f"Not a git repository: {probe}") from None
    return Path(out.strip())


def git_status(repo_path: str | None = None) -> dict[str, Any]:
    repo = resolve_repo(repo_path)
    branch = _run(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    sha = _run(repo, "rev-parse", "HEAD").strip()
    dirty = bool(_run(repo, "status", "--porcelain").strip())
    return {
        "repo": str(repo),
        "branch": branch,
        "sha": sha,
        "dirty": dirty,
    }


def list_branches(repo_path: str | None = None) -> dict[str, Any]:
    repo = resolve_repo(repo_path)
    raw = _run(repo, "branch", "-a", "--format=%(refname:short)")
    branches = sorted({line.strip() for line in raw.splitlines() if line.strip()})
    current = _run(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return {"repo": str(repo), "current": current, "branches": branches}


def list_tree(
    repo_path: str | None = None,
    *,
    ref: str = "HEAD",
    path: str = "",
) -> dict[str, Any]:
    """List files/dirs at path for a ref (read-only)."""
    repo = resolve_repo(repo_path)
    safe_ref = ref.strip() or "HEAD"
    if ".." in safe_ref or any(c in safe_ref for c in " \t\n;|&"):
        raise GitBrowserError("Unsafe ref")
    prefix = path.strip().lstrip("/")
    if ".." in prefix.split("/"):
        raise GitBrowserError("Unsafe path")
    spec = f"{safe_ref}:{prefix}" if prefix else f"{safe_ref}:"
    raw = _run(repo, "ls-tree", "--name-only", spec)
    entries: list[dict[str, str]] = []
    for name in raw.splitlines():
        name = name.strip()
        if not name:
            continue
        leaf = name.rsplit("/", 1)[-1]
        full = f"{prefix}/{leaf}" if prefix else leaf
        # Detect directory via second ls-tree
        kind = "file"
        try:
            _run(repo, "ls-tree", "--name-only", f"{safe_ref}:{full}")
            # if ls-tree of path as tree succeeds with children OR empty, treat as dir when
            # original ls-tree entry had no extension check — use cat-file
            typ = _run(repo, "cat-file", "-t", f"{safe_ref}:{full}").strip()
            kind = "dir" if typ == "tree" else "file"
        except GitBrowserError:
            kind = "file"
        entries.append({"name": leaf, "path": full, "kind": kind})
    entries.sort(key=lambda e: (0 if e["kind"] == "dir" else 1, e["name"]))
    return {
        "repo": str(repo),
        "ref": safe_ref,
        "path": prefix,
        "entries": entries,
    }


def read_file(
    repo_path: str | None = None,
    *,
    ref: str = "HEAD",
    path: str,
    max_bytes: int = 200_000,
) -> dict[str, Any]:
    repo = resolve_repo(repo_path)
    safe_ref = ref.strip() or "HEAD"
    if ".." in safe_ref or any(c in safe_ref for c in " \t\n;|&"):
        raise GitBrowserError("Unsafe ref")
    rel = path.strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise GitBrowserError("Unsafe path")
    try:
        content = _run(repo, "show", f"{safe_ref}:{rel}", timeout=10.0)
    except GitBrowserError as exc:
        raise GitBrowserError(f"Cannot read {rel}: {exc}") from exc
    truncated = False
    if len(content.encode("utf-8", errors="replace")) > max_bytes:
        content = content.encode("utf-8", errors="replace")[:max_bytes].decode(
            "utf-8", errors="replace"
        )
        truncated = True
    return {
        "repo": str(repo),
        "ref": safe_ref,
        "path": rel,
        "content": content,
        "truncated": truncated,
    }
