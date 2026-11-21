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

- Filtering inside nested warehouse data (Snowflake VARIANT paths, BigQuery STRUCT fields)
- GraphQL subscription push (CDC) beyond poll MVP
- dbt exposures / tests → OpenAPI metadata

## Business rules: what the API does and where the limits are

Each rule is a spec option and a Studio control; defaults keep the simple behaviour.

| Need | Option | Limit |
|------|--------|-------|
| Save a row with its children atomically | `nested_writes` (one_to_many relations) | One level deep, create only (POST), max 100 children per relation, REST only (not GraphQL / bulk / async writes). Children get no timestamps or defaults of their own |
| Bulk create all-or-nothing | `bulk_atomic: true` | Max 100 rows; `reuse_deleted` does not apply inside an atomic bulk |
| API sets created/updated times | `timestamps` | Rows changed outside the API keep whatever the database sets |
| Defaults / values callers cannot change | `defaults`, `fixed_values` | Constant values only (no expressions or lookups) |
| Bring back / reuse deleted rows | `soft_delete.restore`, `soft_delete.reuse_deleted` | Reuse matches the table's unique constraints/indexes. It revives the same record: its id, omitted columns and children (e.g. orders) come back with it |
| Exact money values | `app.decimals: string` | Applies to the whole API, not per field |
| Date-times with a zone | `database.timezone` | One zone per database; async-job results use the stored value as is |
| Notice renamed/dropped columns | 409 `schema-changed` + Studio **Check database changes** | Checked on request or on demand, not pushed to you |
| Snowflake/BigQuery nested data | automatic | Returned as JSON only: no filter, sort or write on those columns; GraphQL returns VARIANT as text |

Not offered on purpose: **custom code hooks** (running user Python on the server). Rules that need
logic beyond the above belong in the database: views, constraints, triggers, or a custom SQL
endpoint for reads. Writes still target one table plus its nested children.

## Not in scope

- Multi-org SaaS control plane / billing
- Managed cloud hosting
- Real-time collaboration

PyPI package name: **`contractapi`** (import `contractapi`).
