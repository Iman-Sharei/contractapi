# Remaining gaps (post-Beta)

**Maturity:** Beta `0.5.0` — see [STABILITY.md](STABILITY.md).

## Experimental

No features currently require `CONTRACTAPI_EXPERIMENTAL`. The env var remains for future opt-ins; `all` / legacy tokens are ignored.

## GA (config / optional extras only)

| Feature | Enable with |
|---------|-------------|
| Parquet list export | `pip install 'contractapi[parquet]'` + `parquet_export: true` |
| DuckDB driver | `pip install 'contractapi[duckdb]'` + `database.driver: duckdb` |
| Snowflake / BigQuery | `pip install 'contractapi[snowflake]'` / `[bigquery]` + `database.driver` |
| GraphQL facade | `pip install 'contractapi[graphql]'` → `/graphql` (reads + RLS claims + mutations + poll subscriptions) |
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
- PKCE for public OIDC clients

## Not in scope

- Multi-org SaaS control plane / billing
- Managed cloud hosting
- Real-time collaboration

PyPI package name: **`contractapi`** (import `contractapi`).
