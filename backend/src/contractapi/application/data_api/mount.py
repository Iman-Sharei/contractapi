"""Mount one spec endpoint: reflect its table, check the contract, add the routes it opted into."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import MetaData, Table
from sqlalchemy.engine import Engine

from contractapi.application.data_api.reads import _add_detail, _add_list
from contractapi.application.data_api.restore import _add_restore
from contractapi.application.data_api.updates import _add_delete, _add_update
from contractapi.application.data_api.write_models import _build_create_model, _build_write_models
from contractapi.application.data_api.write_rules import (
    NestedTables,
    missing_managed_columns,
    unique_column_sets,
)
from contractapi.application.data_api.writes import _add_bulk, _add_create
from contractapi.application.warehouse_types import prepare_nested_columns
from contractapi.domain.models.spec import ApiSpec, EndpointSpec, HttpMethod
from contractapi.infrastructure.db.introspect import resolve_schema


def _reflect(engine: Engine, metadata: MetaData, name: str, schema: str) -> Table:
    return Table(name, metadata, schema=resolve_schema(engine, schema), autoload_with=engine)


def _nested_tables(engine: Engine, metadata: MetaData, endpoint: EndpointSpec) -> NestedTables:
    out: NestedTables = {}
    relations = {r.name: r for r in endpoint.relations}
    for name in endpoint.nested_writes:
        rel = relations[name]
        ctable = _reflect(engine, metadata, rel.table, rel.schema_name)
        missing = [c for c in {*rel.fields, rel.foreign_key, rel.primary_key} if c not in ctable.c]
        if missing:
            raise ValueError(
                f"Endpoint '{endpoint.name}': nested relation '{name}' needs columns missing on "
                f"{rel.table}: {', '.join(sorted(missing))}"
            )
        out[name] = (rel, ctable)
    return out


def _mount_endpoint(
    router: APIRouter,
    engine: Engine,
    metadata: MetaData,
    endpoint: EndpointSpec,
    spec: ApiSpec,
) -> None:
    if endpoint.is_sql:
        from contractapi.application.sql_endpoint import mount_sql_endpoint

        mount_sql_endpoint(router, engine, endpoint, spec)
        return

    table = _reflect(engine, metadata, endpoint.table, endpoint.schema_name)
    missing = [f for f in endpoint.fields if f not in table.c]
    if not spec.app.read_only and endpoint.allows_writes:
        missing += [c for c in missing_managed_columns(table, endpoint) if c not in missing]
    if missing:
        raise ValueError(
            f"Endpoint '{endpoint.name}': missing columns on "
            f"{endpoint.schema_name}.{endpoint.table}: {', '.join(missing)}"
        )
    prepare_nested_columns(table, endpoint, spec.database.driver)

    tags = [endpoint.name]
    if HttpMethod.GET in endpoint.methods:
        _add_list(router, engine, metadata, table, endpoint, spec, tags)
        _add_detail(router, engine, metadata, table, endpoint, spec, tags)

    if spec.app.read_only:
        return

    decimals = spec.app.decimals
    item_model, _, write_model = _build_write_models(endpoint, table, decimals=decimals)
    sd = endpoint.soft_delete
    unique_sets = unique_column_sets(table) if sd and sd.reuse_deleted else []
    if HttpMethod.POST in endpoint.methods:
        nested = _nested_tables(engine, metadata, endpoint)
        _add_create(
            router, engine, table, endpoint, spec, item_model, write_model, tags,
            create_model=_build_create_model(endpoint, write_model, nested, decimals=decimals),
            nested=nested,
            unique_sets=unique_sets,
        )
        if endpoint.bulk_enabled:
            _add_bulk(router, engine, table, endpoint, spec, write_model, tags, unique_sets=unique_sets)
    if HttpMethod.PUT in endpoint.methods or HttpMethod.PATCH in endpoint.methods:
        _add_update(router, engine, table, endpoint, spec, item_model, write_model, tags)
    if HttpMethod.DELETE in endpoint.methods:
        _add_delete(router, engine, table, endpoint, spec, tags)
        if sd and sd.restore:
            _add_restore(router, engine, table, endpoint, spec, tags)
