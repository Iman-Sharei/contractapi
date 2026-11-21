"""Database engine factory — Postgres (default), MySQL, SQL Server, DuckDB and warehouses."""

from __future__ import annotations

from functools import lru_cache
from threading import Lock

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import DatabaseConfig, DatabaseDriver


def normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def create_pg_engine(url: str, *, pooled: bool = True) -> Engine:
    from contractapi.infrastructure.secrets import resolve_refs

    settings = get_settings()
    url = normalize_postgres_url(resolve_refs(url))
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
        # One-off checks (introspect, preview, readiness): close connections on release.
        engine = create_engine(url, poolclass=NullPool, connect_args=connect_args)

    @event.listens_for(engine, "connect")
    def _set_timeout(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute(f"SET statement_timeout = {settings.db_statement_timeout_ms}")
            cursor.close()
        except Exception:  # noqa: BLE001, S110 — e.g. poolers rejecting SET; connect_args already set it
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
    _require("duckdb", "duckdb", "DuckDB")

    # Accept raw paths and duckdb:// URLs.
    # :memory: uses StaticPool so every checkout hits the same in-process DB.
    from sqlalchemy.pool import StaticPool

    memory = False
    if url.startswith("duckdb:///"):
        path = url[len("duckdb:///") :].split("?", 1)[0]
        if path in {":memory:", "memory", ""}:
            sa_url = "duckdb:///:memory:"
            memory = True
        else:
            sa_url = f"duckdb:///{path}"
    elif url.startswith("duckdb://"):
        sa_url = url.split("?", 1)[0]
        memory = "/:memory:" in sa_url or sa_url.rstrip("/").endswith(":memory:")
    elif url in {":memory:", "memory"}:
        sa_url = "duckdb:///:memory:"
        memory = True
    else:
        sa_url = f"duckdb:///{url}"

    if memory:
        return create_engine(sa_url, poolclass=StaticPool)
    return create_engine(sa_url)


def create_snowflake_engine(url: str) -> Engine:
    """Snowflake via snowflake-sqlalchemy. URL: snowflake://user:pass@account/db/schema."""
    _require("snowflake.sqlalchemy", "snowflake", "Snowflake")
    return create_engine(url)


def create_bigquery_engine(url: str) -> Engine:
    """
    BigQuery via sqlalchemy-bigquery.
    URL examples:
      bigquery://project/dataset
      bigquery://project/dataset?credentials_path=/path/key.json
    """
    _require("sqlalchemy_bigquery", "bigquery", "BigQuery")
    return create_engine(url)


def _require(module: str, extra: str, label: str) -> None:
    import importlib

    try:
        importlib.import_module(module)
    except ImportError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/dependency-missing",
            title="Database driver not installed",
            status=400,
            detail=f"{label} support is not installed on the server. "
            f"Install it with: pip install 'contractapi[{extra}]'",
        ) from exc


def normalize_mysql_url(url: str) -> str:
    scheme, rest = url.split("://", 1)
    if "+" not in scheme:
        scheme = "mysql+pymysql"
    if "charset=" not in rest:
        rest += ("&" if "?" in rest else "?") + "charset=utf8mb4"
    return f"{scheme}://{rest}"


def normalize_sqlserver_url(url: str) -> str:
    scheme, rest = url.split("://", 1)
    if "+" not in scheme:
        scheme = "mssql+pymssql"
    return f"{scheme.replace('sqlserver', 'mssql')}://{rest}"


def _pool_args(pooled: bool) -> dict:
    settings = get_settings()
    if not pooled:
        # One-off checks (introspect, preview, readiness): close connections on release.
        return {"poolclass": NullPool}
    return {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": 1800,  # MySQL/SQL Server drop idle connections (wait_timeout)
    }


def create_mysql_engine(url: str, *, pooled: bool = True) -> Engine:
    """MySQL / MariaDB via PyMySQL. URL: mysql://user:pass@host:3306/database"""
    _require("pymysql", "mysql", "MySQL")
    timeout_ms = get_settings().db_statement_timeout_ms
    engine = create_engine(
        normalize_mysql_url(url),
        # "name" means a column (standard SQL), as in every other supported database. Set as
        # the connection opens, so SQLAlchemy sees it and reads table definitions correctly.
        connect_args={"init_command": "SET SESSION sql_mode = CONCAT(@@sql_mode, ',ANSI_QUOTES')"},
        **_pool_args(pooled),
    )

    @event.listens_for(engine, "connect")
    def _timeout(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:  # MySQL only (MariaDB names it max_statement_time); limits SELECTs.
            cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}")
        except Exception:  # noqa: BLE001, S110
            pass
        cursor.close()

    return engine


def create_sqlserver_engine(url: str, *, pooled: bool = True) -> Engine:
    """SQL Server via pymssql. URL: mssql://user:pass@host:1433/database"""
    _require("pymssql", "sqlserver", "SQL Server")
    timeout_s = max(1, round(get_settings().db_statement_timeout_ms / 1000))
    return create_engine(
        normalize_sqlserver_url(url),
        connect_args={"timeout": timeout_s, "login_timeout": 10},
        **_pool_args(pooled),
    )


_shared: dict[tuple[str, str], Engine] = {}
_shared_lock = Lock()


_SERVER_ENGINES = {
    DatabaseDriver.POSTGRES: create_pg_engine,
    DatabaseDriver.MYSQL: create_mysql_engine,
    DatabaseDriver.SQLSERVER: create_sqlserver_engine,
}


def create_engine_for_config(config: DatabaseConfig, *, pooled: bool = True) -> Engine:
    """Engine for a spec's database. Pooled server engines are shared per URL so
    rebuilding/previewing APIs does not open a new connection pool each time."""
    from contractapi.infrastructure.secrets import resolve_refs

    url = resolve_refs(config.url)
    if config.driver == DatabaseDriver.DUCKDB:
        return create_duckdb_engine(url)
    if config.driver == DatabaseDriver.SNOWFLAKE:
        return create_snowflake_engine(url)
    if config.driver == DatabaseDriver.BIGQUERY:
        return create_bigquery_engine(url)
    factory = _SERVER_ENGINES[config.driver]
    if not pooled:
        return factory(url, pooled=False)
    key = (url, config.driver.value)
    with _shared_lock:
        engine = _shared.get(key)
        if engine is None:
            engine = _shared[key] = factory(url, pooled=True)
        return engine


def create_engine_for_url(url: str, *, pooled: bool = False) -> Engine:
    """Engine for a bare URL (Studio introspect / checks); the driver comes from the scheme."""
    return create_engine_for_config(DatabaseConfig(url=url), pooled=pooled)


@lru_cache(maxsize=8)
def get_cached_engine(url: str) -> Engine:
    return create_pg_engine(url)
