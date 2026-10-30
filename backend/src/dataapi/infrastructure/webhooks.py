"""Webhooks on write events — retries with backoff + JSONL DLQ."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from dataapi.core.config import get_settings
from dataapi.core.logging import get_logger
from dataapi.domain.models.spec import ApiSpec, WebhookConfig

logger = get_logger("dataapi.webhooks")

_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)


def dispatch_webhooks(
    spec: ApiSpec,
    *,
    event: str,
    endpoint: str,
    payload: dict[str, Any],
) -> None:
    hooks = [h for h in spec.app.webhooks if event in h.events]
    if not hooks:
        return
    body = json.dumps(
        {"event": event, "endpoint": endpoint, "data": payload},
        default=str,
        separators=(",", ":"),
    ).encode()

    for hook in hooks:
        threading.Thread(
            target=_send_with_retries,
            args=(hook, body, event, endpoint),
            daemon=True,
        ).start()


def _dlq_path() -> Path:
    settings = get_settings()
    root = Path(settings.specs_dir) / ".runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root / "webhook-dlq.jsonl"


def _append_dlq(record: dict[str, Any]) -> None:
    path = _dlq_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def _send_with_retries(
    hook: WebhookConfig,
    body: bytes,
    event: str,
    endpoint: str,
) -> None:
    last_err: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            _send_once(hook, body)
            if attempt:
                logger.info(
                    "webhook recovered url=%s event=%s attempt=%s",
                    hook.url,
                    event,
                    attempt + 1,
                )
            return
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            logger.warning(
                "webhook attempt failed url=%s attempt=%s err=%s",
                hook.url,
                attempt + 1,
                exc,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])
    _append_dlq(
        {
            "ts": time.time(),
            "url": hook.url,
            "event": event,
            "endpoint": endpoint,
            "error": last_err,
            "body": body.decode("utf-8", errors="replace"),
        }
    )
    logger.error("webhook exhausted retries → DLQ url=%s event=%s", hook.url, event)


def _send_once(hook: WebhookConfig, body: bytes) -> None:
    headers = {"Content-Type": "application/json", "User-Agent": "dataapi-webhook/1"}
    if hook.secret:
        sig = hmac.new(hook.secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Dataapi-Signature"] = f"sha256={sig}"
    req = urlrequest.Request(hook.url, data=body, headers=headers, method="POST")
    with urlrequest.urlopen(req, timeout=hook.timeout_seconds) as resp:  # noqa: S310
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status}")
        logger.info("webhook ok url=%s status=%s", hook.url, resp.status)
