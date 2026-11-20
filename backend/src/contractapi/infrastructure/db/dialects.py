"""The few SQL differences between the databases contractapi talks to.

Raw SQL in the data plane (custom SQL endpoints, filters, relations, GraphQL) goes through
these helpers instead of writing Postgres syntax directly. Identifiers are always validated
by the caller and double-quoted: Postgres, SQL Server and DuckDB read `"name"` as a column,
and MySQL does too because every MySQL connection turns on ANSI_QUOTES (see engine.py).
"""

from __future__ import annotations

from typing import Any

POSTGRES = "postgresql"
MYSQL = "mysql"
MSSQL = "mssql"


def dialect_of(bind: Any) -> str:
    """SQLAlchemy dialect name of an Engine or Connection ("postgresql", "mysql", "mssql", …)."""
    return bind.dialect.name


def table_schema(dialect: str, schema: str | None, *, database: str | None = None) -> str | None:
    """Schema to use for a table. `public` is Postgres' default and means "the default
    schema" elsewhere: the connected database on MySQL, `dbo` on SQL Server."""
    if schema in (None, ""):
        schema = "public"
    if dialect == MYSQL and schema == "public":
        return database or None
    if dialect == MSSQL and schema == "public":
        return "dbo"
    return schema


def page_sql(dialect: str, *, offset: bool) -> str:
    """Paging clause appended after an ORDER BY. Binds :_limit (and :_offset)."""
    if dialect == MSSQL:
        start = ":_offset" if offset else "0"
        return f" OFFSET {start} ROWS FETCH NEXT :_limit ROWS ONLY"
    return " LIMIT :_limit OFFSET :_offset" if offset else " LIMIT :_limit"


def first_row_sql(dialect: str, select_from: str, order_by: str) -> str:
    """`SELECT … FROM … WHERE …` limited to one row (SQL Server needs an ORDER BY for that)."""
    if dialect == MSSQL:
        return f"{select_from} ORDER BY {order_by} OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY"
    return f"{select_from} LIMIT 1"


def no_rows_sql(dialect: str, inner: str) -> str:
    """Query that returns the columns of `inner` and no rows."""
    if dialect == MSSQL:
        return f"SELECT TOP 0 * FROM ({inner}) AS q"
    return f"SELECT * FROM ({inner}) AS q LIMIT 0"


def as_text_sql(dialect: str, col: str) -> str:
    """`col` as text, for comparing with a path value (always a string)."""
    if dialect == MYSQL:
        return f"CAST({col} AS CHAR)"
    if dialect == MSSQL:
        return f"CAST({col} AS NVARCHAR(4000))"
    return f"CAST({col} AS TEXT)"


def contains_sql(dialect: str, col: str, param: str) -> str:
    """Case-insensitive `col LIKE :param` with `\\` as the escape character."""
    if dialect == MYSQL:
        # Backslash is an escape inside MySQL string literals, so the literal needs two.
        return f"LOWER(CAST({col} AS CHAR)) LIKE LOWER(:{param}) ESCAPE '\\\\'"
    if dialect == MSSQL:
        return f"LOWER(CAST({col} AS NVARCHAR(MAX))) LIKE LOWER(:{param}) ESCAPE '\\'"
    return f"CAST({col} AS TEXT) ILIKE :{param} ESCAPE '\\'"


def can_return_rows(bind: Any, *, update: bool = False) -> bool:
    """Does INSERT/UPDATE … RETURNING work here? (No on MySQL.)"""
    d = bind.dialect
    return bool(d.update_returning if update else d.insert_returning)


def insert_returning(conn: Any, table: Any, payload: dict[str, Any], fields: list[str], pk: str) -> Any:
    """INSERT and return the stored row (with defaults and generated ids), on every database.

    Where RETURNING is unavailable (MySQL), the new id comes from the driver and the row is
    read back inside the same transaction."""
    from sqlalchemy import select

    cols = [table.c[f] for f in fields]
    if can_return_rows(conn):
        return conn.execute(table.insert().values(**payload).returning(*cols)).mappings().first()
    result = conn.execute(table.insert().values(**payload))
    key = payload.get(pk)
    if key is None and result.inserted_primary_key:
        key = result.inserted_primary_key[0]
    if key is None:
        return None
    return conn.execute(select(*cols).where(table.c[pk] == key)).mappings().first()


def update_returning(conn: Any, table: Any, where: Any, payload: dict[str, Any], fields: list[str]) -> Any:
    """UPDATE … WHERE and return the updated row, or None when nothing matched."""
    from sqlalchemy import select

    cols = [table.c[f] for f in fields]
    stmt = table.update().where(where).values(**payload)
    if can_return_rows(conn, update=True):
        return conn.execute(stmt.returning(*cols)).mappings().first()
    if conn.execute(stmt).rowcount == 0:  # MySQL: SQLAlchemy asks for "matched", not "changed"
        return None
    return conn.execute(select(*cols).where(where)).mappings().first()
