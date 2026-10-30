"""Database engine factory — Postgres (default) + DuckDB warehouse MVP."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from dataapi.core.config import get_settings
from dataapi.domain.models.spec import DatabaseConfig, DatabaseDriver


def normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def create_pg_engine(url: str, *, pooled: bool = True) -> Engine:
    settings = get_settings()
    url = normalize_postgres_url(url)
    connect_args: dict = {}
    connect_args["options"] = f"-c statement_timeout={settings.db_statement_timeout_ms}"

    if pooled:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            connect_args=connect_args,
        )
    else:
        engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)

    @event.listens_for(engine, "connect")
    def _set_timeout(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute(f"SET statement_timeout = {settings.db_statement_timeout_ms}")
            cursor.close()
        except Exception:
            pass

    return engine


def create_duckdb_engine(url: str) -> Engine:
    """
    DuckDB via SQLAlchemy (read-oriented warehouse / Parquet local file MVP).

    URL examples:
      duckdb:///:memory:
      duckdb:///./analytics.duckdb
      duckdb:////abs/path/warehouse.duckdb
    """
    try:
        import duckdb  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Install DuckDB support with: pip install 'dataapi[duckdb]'") from exc

    # Accept raw paths and duckdb:// URLs
    if url.startswith("duckdb:///"):
        path = url[len("duckdb:///") :]
        sa_url = f"duckdb:///{path}"
    elif url.startswith("duckdb://"):
        sa_url = url
    elif url in {":memory:", "memory"}:
        sa_url = "duckdb:///:memory:"
    else:
        sa_url = f"duckdb:///{url}"

    return create_engine(sa_url)


def create_engine_for_config(config: DatabaseConfig, *, pooled: bool = True) -> Engine:
    if config.driver == DatabaseDriver.DUCKDB:
        from dataapi.core.config import get_settings

        if not get_settings().experimental_enabled("duckdb"):
            raise RuntimeError(
                "DuckDB driver is experimental — set DATAAPI_EXPERIMENTAL=duckdb (or all)"
            )
        return create_duckdb_engine(config.url)
    return create_pg_engine(config.url, pooled=pooled)


@lru_cache(maxsize=8)
def get_cached_engine(url: str) -> Engine:
    return create_pg_engine(url)
