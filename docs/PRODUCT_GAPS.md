# Remaining gaps (post-Beta)

**Maturity:** Beta `0.6.1` — see [STABILITY.md](STABILITY.md).

## Experimental

No features currently require `CONTRACTAPI_EXPERIMENTAL`. The env var remains for future opt-ins; `all` / legacy tokens are ignored.

## GA (config / optional extras only)

| Feature | Enable with |
|---------|-------------|
| Parquet list export | `pip install 'contractapi[parquet]'` + `parquet_export: true` |
| MySQL / SQL Server | `pip install 'contractapi[mysql]'` / `[sqlserver]`; driver inferred from the URL |
| DuckDB driver | `pip install 'contractapi[duckdb]'` + `database.driver: duckdb` |
| Snowflake / BigQuery | `pip install 'contractapi[snowflake]'` / `[bigquery]` + `database.driver` |
| GraphQL facade | `pip install 'contractapi[graphql]'` → `/graphql` (reads + token-based RLS/RBAC + mutations + poll subscriptions) |
| Aggregation DSL | `aggregate:` with group_by, metrics, where, having, windows |
| Studio OIDC (JWKS + cookie BFF) | `STUDIO_OIDC_ISSUER` (+ client_id / redirect_uri for browser cookies) |
| Redis job queue | `JOB_QUEUE_ENABLED=true` + `REDIS_URL` (+ `contractapi worker`) |
| Multi-active mounts | Always on: primary `/data` + `/apis/{name}` |
| dbt → endpoints | `POST /studio/import/dbt` (schema.yml or manifest.json) |
| Git branch browser | `GET /studio/git/{status,branches,tree,file}` (+ Studio Tools UI) |

## Nice-to-have later (not blocking Beta)

- Deeper warehouse dialect quirks (Snowflake VARIANT, BQ STRUCT nesting)
- GraphQL subscription push (CDC) beyond poll MVP
- dbt exposures / tests → OpenAPI metadata

## Business-logic limits (found in the 2026-11-20 user walkthrough)

What a data team should know before relying on the generated API for real business rules:

- **Writes touch one table at a time.** No multi-table transactions, no custom code hooks;
  complex rules belong in the database (views, constraints, triggers).
- **Bulk create is per row**, not all-or-nothing: valid rows are stored, the rest are reported
  (HTTP 207).
- **`updated_at` is not set by the API.** If `etag_field` is a timestamp, the database must
  update it (trigger / `ON UPDATE`), or `If-Match` cannot detect concurrent edits. Without
  `etag_field`, the ETag is a hash of the row and works everywhere.
- **Decimals are JSON numbers.** Values beyond ~15 significant digits lose precision; a
  "decimals as text" option would fix this for finance data.
- **Soft-deleted rows still hold unique values** (a deleted email cannot be reused).
- **Schema changes are not tracked live**: a renamed or dropped column is caught when the API
  is activated or restarted ("missing columns"), not while it runs.
- **MySQL `DATETIME` has no time zone**, so those values are returned without an offset.

## Not in scope

- Multi-org SaaS control plane / billing
- Managed cloud hosting
- Real-time collaboration

PyPI package name: **`contractapi`** (import `contractapi`).
