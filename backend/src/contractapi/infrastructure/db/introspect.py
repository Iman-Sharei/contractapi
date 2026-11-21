"""Schema introspection via SQLAlchemy reflection (Postgres, MySQL, SQL Server, DuckDB)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from sqlalchemy import MetaData, Table, inspect
from sqlalchemy.engine import Engine

from contractapi.domain.sensitive import find_sensitive_columns
from contractapi.infrastructure.db.dialects import dialect_of, table_schema
from contractapi.infrastructure.db.engine import create_engine_for_url

# MySQL / SQL Server append storage details ("VARCHAR(200) COLLATE ..."), noise in Studio.
_TYPE_SUFFIX = re.compile(r"\s+(COLLATE|CHARACTER SET|CHARSET)\b.*$", re.IGNORECASE)


def type_label(col_type: object) -> str:
    """Readable column type: ``VARCHAR(200)``, without collation or charset."""
    return _TYPE_SUFFIX.sub("", str(col_type))


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    primary_key: bool
    sensitive: bool = False
    comment: str | None = None


@dataclass
class TableInfo:
    name: str
    schema: str
    kind: str = "table"  # table | view
    columns: list[ColumnInfo] = field(default_factory=list)
    foreign_keys: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "schema": self.schema,
            "kind": self.kind,
            "columns": [asdict(c) for c in self.columns],
            "foreign_keys": self.foreign_keys,
            "primary_keys": [c.name for c in self.columns if c.primary_key],
            "sensitive_columns": [c.name for c in self.columns if c.sensitive],
        }


def introspect_schema(url: str, schema: str = "public") -> list[TableInfo]:
    engine = create_engine_for_url(url)
    return introspect_with_engine(engine, schema=schema)


def resolve_schema(engine: Engine, schema: str | None) -> str | None:
    """`public` → the default schema of this database (database name on MySQL, dbo on SQL Server)."""
    return table_schema(dialect_of(engine), schema, database=engine.url.database)


def introspect_with_engine(engine: Engine, schema: str = "public") -> list[TableInfo]:
    inspector = inspect(engine)
    schema = resolve_schema(engine, schema)  # type: ignore[assignment]
    tables: list[TableInfo] = []
    for table_name in inspector.get_table_names(schema=schema):
        tables.append(_build_table_info(inspector, table_name, schema, kind="table"))
    for view_name in inspector.get_view_names(schema=schema):
        tables.append(_build_table_info(inspector, view_name, schema, kind="view"))
    return tables


def _build_table_info(
    inspector: object, name: str, schema: str, *, kind: str = "table"
) -> TableInfo:
    get_pk = inspector.get_pk_constraint
    get_columns = inspector.get_columns
    get_fks = inspector.get_foreign_keys

    columns: list[ColumnInfo] = []
    pk = set(get_pk(name, schema=schema).get("constrained_columns") or [])

    for col in get_columns(name, schema=schema):
        col_name = col["name"]
        columns.append(
            ColumnInfo(
                name=col_name,
                type=type_label(col["type"]),
                nullable=bool(col.get("nullable", True)),
                primary_key=col_name in pk,
                sensitive=bool(find_sensitive_columns([col_name])),
                comment=(col.get("comment") or None),
            )
        )

    fks: list[dict[str, str]] = []
    for fk in get_fks(name, schema=schema):
        referred = fk.get("referred_table") or ""
        constrained = list(fk.get("constrained_columns") or [])
        referred_cols = list(fk.get("referred_columns") or [])
        for local_col, remote_col in zip(constrained, referred_cols, strict=False):
            fks.append(
                {
                    "column": local_col,
                    "ref_table": referred,
                    "ref_column": remote_col,
                }
            )

    return TableInfo(name=name, schema=schema, kind=kind, columns=columns, foreign_keys=fks)


def get_table(engine: Engine, table: str, schema: str = "public") -> Table:
    metadata = MetaData()
    return Table(table, metadata, schema=resolve_schema(engine, schema), autoload_with=engine)


def missing_columns(url: str, table: str, schema: str, fields: list[str]) -> list[str]:
    engine = create_engine_for_url(url)
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns(table, schema=resolve_schema(engine, schema))}
    return [f for f in fields if f not in existing]
