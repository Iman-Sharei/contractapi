"""Durable JSON job payloads for horizontal workers (no pickle)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, Table

from dataapi.application.jobs import register_payload_handler
from dataapi.core.logging import get_logger
from dataapi.domain.models.spec import DatabaseConfig, DatabaseDriver, EndpointSpec, HttpMethod
from dataapi.infrastructure.db.engine import create_engine_for_config

logger = get_logger("dataapi.job_handlers")


def _engine_from_payload(payload: dict[str, Any]):
    driver = payload.get("driver") or "postgres"
    try:
        drv = DatabaseDriver(driver)
    except ValueError:
        drv = DatabaseDriver.POSTGRES
    return create_engine_for_config(DatabaseConfig(url=payload["database_url"], driver=drv))


def handle_insert(payload: dict[str, Any]) -> dict[str, Any]:
    from dataapi.application import data_api_builder as dab

    engine = _engine_from_payload(payload)
    metadata = MetaData()
    table = Table(
        payload["table"],
        metadata,
        schema=payload.get("schema") or "public",
        autoload_with=engine,
    )
    endpoint = EndpointSpec(
        name=payload.get("endpoint_name") or payload["table"],
        path=payload.get("path") or f"/{payload['table']}",
        table=payload["table"],
        schema=payload.get("schema") or "public",
        methods=[HttpMethod.POST],
        fields=payload["fields"],
        primary_key=payload.get("primary_key") or "id",
        writable_fields=list(payload.get("row", {}).keys()),
    )
    return dab._do_insert(engine, table, endpoint, payload["row"])


def register_default_handlers() -> None:
    register_payload_handler("insert", handle_insert)
    logger.info("Registered durable job handler: insert")
