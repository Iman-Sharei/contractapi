"""Async job registry — in-process by default; Redis-backed for horizontal workers."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from contractapi.core.config import get_settings
from contractapi.core.logging import get_logger

logger = get_logger("contractapi.jobs")

JOB_TTL_SECONDS = 86_400


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued|running|succeeded|failed
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    kind: str | None = None
    payload: dict[str, Any] | None = None


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_local_fns: dict[str, Callable[[], Any]] = {}


def _job_key(job_id: str) -> str:
    return f"contractapi:job:{job_id}"


def _persist(job: Job) -> None:
    settings = get_settings()
    if not settings.redis_url:
        return
    try:
        from contractapi.infrastructure.kv import kv_json_set

        kv_json_set(
            _job_key(job.id),
            {
                "id": job.id,
                "status": job.status,
                "result": job.result,
                "error": job.error,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "kind": job.kind,
                "payload": job.payload,
            },
            JOB_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist job %s: %s", job.id, exc)


def _load_remote(job_id: str) -> Job | None:
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        from contractapi.infrastructure.kv import kv_json_get

        raw = kv_json_get(_job_key(job_id))
        if not raw:
            return None
        return Job(
            id=raw["id"],
            status=raw.get("status", "queued"),
            result=raw.get("result"),
            error=raw.get("error"),
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
            kind=raw.get("kind"),
            payload=raw.get("payload"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load job %s: %s", job_id, exc)
        return None


def create_job(*, kind: str | None = None, payload: dict[str, Any] | None = None) -> Job:
    job = Job(id=str(uuid.uuid4()), kind=kind, payload=payload)
    with _lock:
        _jobs[job.id] = job
    _persist(job)
    return job


def get_job(job_id: str) -> Job | None:
    with _lock:
        local = _jobs.get(job_id)
    if local:
        return local
    remote = _load_remote(job_id)
    if remote:
        with _lock:
            _jobs[job_id] = remote
        return remote
    return None


def _set_status(job_id: str, *, status: str, result: Any = None, error: str | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            job = Job(id=job_id)
            _jobs[job_id] = job
        job.status = status
        job.result = result
        job.error = error
        job.updated_at = time.time()
        snapshot = Job(
            id=job.id,
            status=job.status,
            result=job.result,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
            kind=job.kind,
            payload=job.payload,
        )
    _persist(snapshot)


def run_job(job_id: str, fn: Callable[[], Any]) -> None:
    """Run immediately in a daemon thread (default / no Redis queue)."""

    def _worker() -> None:
        _set_status(job_id, status="running")
        try:
            result = fn()
            _set_status(job_id, status="succeeded", result=result)
        except Exception as exc:  # noqa: BLE001
            _set_status(job_id, status="failed", error=str(exc))

    threading.Thread(target=_worker, daemon=True).start()


def enqueue_job(job_id: str, fn: Callable[[], Any]) -> None:
    """
    Prefer Redis list when JOB_QUEUE_ENABLED + REDIS_URL; otherwise local thread.

    Horizontal workers call `process_next_job` / `contractapi worker` and execute
    the JSON payload via registered handlers. Callables still run locally when
    the queue is disabled — DX for single-node stays identical.
    """
    settings = get_settings()
    if settings.job_queue_enabled and settings.redis_url:
        with _lock:
            job = _jobs.get(job_id)
            if job and job.payload:
                _local_fns[job_id] = fn  # same-process worker shortcut
                _persist(job)
                try:
                    import redis

                    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                    client.lpush(
                        settings.job_queue_key,
                        json.dumps({"job_id": job_id, "kind": job.kind, "payload": job.payload}),
                    )
                    logger.info("Enqueued job %s on %s", job_id, settings.job_queue_key)
                    return
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Queue push failed (%s); falling back to local thread", exc)
    run_job(job_id, fn)


def process_next_job(*, timeout_seconds: int = 5) -> str | None:
    """
    BRPOP one job from Redis and run it.

    Prefers an in-process registered callable (API node that also runs a worker
    thread). External workers need payload handlers registered via
    `register_payload_handler`.
    """
    settings = get_settings()
    if not settings.redis_url:
        return None
    import redis

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    item = client.brpop(settings.job_queue_key, timeout=max(timeout_seconds, 1))
    if not item:
        return None
    _, raw = item
    message = json.loads(raw)
    job_id = message["job_id"]
    fn = _local_fns.pop(job_id, None)
    if fn is None:
        handler = _payload_handlers.get(message.get("kind") or "")
        if handler is None:
            _set_status(
                job_id,
                status="failed",
                error=f"No handler for kind={message.get('kind')!r} on this worker",
            )
            return job_id
        payload = message.get("payload") or {}

        def fn() -> Any:
            return handler(payload)

    _set_status(job_id, status="running")
    try:
        result = fn()
        _set_status(job_id, status="succeeded", result=result)
    except Exception as exc:  # noqa: BLE001
        _set_status(job_id, status="failed", error=str(exc))
    return job_id


_payload_handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}


def register_payload_handler(kind: str, handler: Callable[[dict[str, Any]], Any]) -> None:
    _payload_handlers[kind] = handler


def start_inline_worker() -> None:
    """Background thread that drains the Redis queue (API process)."""
    settings = get_settings()
    if not (settings.job_queue_enabled and settings.redis_url):
        return

    def _loop() -> None:
        while True:
            try:
                process_next_job(timeout_seconds=2)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Job worker loop error: %s", exc)
                time.sleep(1)

    threading.Thread(target=_loop, daemon=True, name="contractapi-job-worker").start()
    logger.info("Inline Redis job worker started")
