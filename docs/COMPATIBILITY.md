# Compatibility matrix

| Component | Supported |
|-----------|-----------|
| Python | **3.10, 3.11, 3.12** (3.13 best-effort) |
| PostgreSQL | **14–16** (tests on 16) |
| MySQL | **8.0–8.4** (tests on 8.4); MariaDB 10.5+ expected to work, untested |
| SQL Server | **2019–2022** (tests on 2022) |
| Redis | **6+** optional (cache, idempotency, jobs) |
| Node.js (Studio) | **20 LTS** |
| Next.js Studio | 15.x as shipped in `apps/web` |

## Optional extras

| Extra | Package |
|-------|---------|
| `pip install 'contractapi[redis]'` | shared KV / queue |
| `pip install 'contractapi[parquet]'` | Parquet export |
| `pip install 'contractapi[mysql]'` | MySQL driver (PyMySQL) |
| `pip install 'contractapi[sqlserver]'` | SQL Server driver (pymssql, no ODBC needed) |
| `pip install 'contractapi[duckdb]'` | DuckDB driver |
| `pip install 'contractapi[graphql]'` | GraphQL at `/graphql` (table+SQL reads, table mutations) |
| `pip install 'contractapi[oidc]'` | cryptography for OIDC |
| `pip install 'contractapi[all]'` | everything |

Import name remains **`contractapi`**; PyPI distribution name is **`contractapi`** (`contractapi` was already taken on PyPI).

## Database notes

- **Same features on PostgreSQL, MySQL and SQL Server**: tables and views, filters and
  `?q=` search (case-insensitive), both paging styles, relations, create / update / delete,
  soft delete, bulk, row-level access, custom SQL with parameters, aggregates, GraphQL.
- **MySQL**: every connection turns on `ANSI_QUOTES`, so in custom SQL write text values with
  single quotes (`'paid'`); `"name"` means a column. The schema is the database name.
  `DATETIME` values have no time zone, so they are returned without an offset.
- **SQL Server**: the default schema is `dbo`. A custom SQL query cannot end with `ORDER BY`
  (the API adds sorting and paging); use `sortable` instead.
- Statement time limit (`DB_STATEMENT_TIMEOUT_MS`): Postgres `statement_timeout`, MySQL
  `MAX_EXECUTION_TIME` (reads), SQL Server driver query timeout.
