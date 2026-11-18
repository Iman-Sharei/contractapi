"""Per-request HTTP metadata: trace ids, metrics, deprecation/rate-limit headers, public paths."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from contractapi.domain.models.spec import (
    ApiSpec,
)
from contractapi.infrastructure.observability import metrics


def _job_owner(spec: ApiSpec, request: Request) -> str:
    principal = getattr(request.state, "principal", {}) or {}
    return f"{spec.namespace}:{principal.get('sub') or 'anon'}"


_TRACE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")


def _ensure_trace(request: Request) -> str:
    """Reuse a caller's trace id only if well-formed (it is echoed in headers and logs)."""
    trace_id = request.headers.get("X-Trace-Id") or ""
    if not _TRACE_ID.match(trace_id):
        m = _TRACEPARENT.match((request.headers.get("traceparent") or "").strip().lower())
        trace_id = m.group(1) if m else uuid.uuid4().hex
    request.state.trace_id = trace_id
    return trace_id


def _decorate_response(response: Response, spec: ApiSpec, trace_id: str, rate_info: Any) -> None:
    response.headers.setdefault("X-Trace-Id", trace_id)
    if rate_info is not None:
        response.headers.setdefault("X-RateLimit-Limit", str(rate_info.limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(rate_info.remaining))
        response.headers.setdefault("X-RateLimit-Reset", str(rate_info.reset_seconds))
    dep = spec.app.deprecation
    if dep.deprecated:
        response.headers.setdefault("Deprecation", "true")
        if dep.sunset:
            response.headers.setdefault("Sunset", dep.sunset)
        link_parts: list[str] = []
        existing = response.headers.get("Link")
        if existing:
            link_parts.append(existing)
        if dep.link:
            link_parts.append(f'<{dep.link}>; rel="deprecation"')
        if dep.successor:
            link_parts.append(f'<{dep.successor}>; rel="successor-version"')
        if link_parts:
            response.headers["Link"] = ", ".join(link_parts)


def _effective_path(request: Request) -> str:
    path = request.scope.get("path") or request.url.path
    # When mounted under /data without clean stripping, normalize.
    if path == "/data":
        return "/"
    if path.startswith("/data/"):
        return path[len("/data") :]
    return path


def _is_public_path(path: str, public_paths: set[str]) -> bool:
    if path in public_paths:
        return True
    # also allow trailing-slash variants
    return bool(path.endswith("/") and path[:-1] in public_paths)


def _record_metrics(method: str, path: str, status: int, duration: float) -> None:
    labels = {"method": method, "path": path, "status": str(status)}
    metrics.incr("contractapi_http_requests_total", labels=labels)
    metrics.observe("contractapi_http_request_duration_seconds", duration, labels={"method": method, "path": path})
