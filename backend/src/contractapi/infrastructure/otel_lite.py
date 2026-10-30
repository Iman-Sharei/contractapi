"""Minimal OpenTelemetry-compatible trace emission (stdout / OTLP HTTP optional)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
from urllib import request as urlrequest

from contractapi.core.config import get_settings
from contractapi.core.logging import get_logger

logger = get_logger("contractapi.otel")


def emit_span(
    *,
    name: str,
    trace_id: str,
    attributes: dict[str, Any] | None = None,
    duration_ms: float | None = None,
    status_code: int | None = None,
) -> None:
    settings = get_settings()
    span = {
        "name": name,
        "traceId": trace_id,
        "spanId": uuid.uuid4().hex[:16],
        "timestamp": time.time(),
        "duration_ms": duration_ms,
        "status_code": status_code,
        "attributes": attributes or {},
        "service": settings.app_name,
        "environment": settings.environment,
    }
    # Always log structured span for local collectors / jq
    logger.info("span %s", json.dumps(span, default=str))
    endpoint = settings.otel_exporter_endpoint
    if not endpoint:
        return
    try:
        body = json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}).encode()
        req = urlrequest.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urlrequest.urlopen(req, timeout=1.5)  # noqa: S310
    except Exception as exc:  # noqa: BLE001
        logger.debug("otel export skipped: %s", exc)
