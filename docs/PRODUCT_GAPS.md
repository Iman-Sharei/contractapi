# Remaining gaps (post-Beta)

**Maturity:** Beta `0.5.0` — see [STABILITY.md](STABILITY.md).

## Experimental (enabled via `CONTRACTAPI_EXPERIMENTAL` / `DATAAPI_EXPERIMENTAL`)

| Feature | Flag |
|---------|------|
| Studio OIDC | `oidc` |
| Redis job queue | `queue` |
| Multi-active `/apis/{name}` | `multi_active` |

Default: `all`.

**GA (no experimental flag):**

- Parquet list export (`parquet_export` / `?format=parquet`) — `pip install 'contractapi[parquet]'`
- DuckDB driver (`database.driver: duckdb`) — `pip install 'contractapi[duckdb]'`
- GraphQL read facade (`/graphql` on the data plane) — `pip install 'contractapi[graphql]'`

## Nice-to-have later (not blocking Beta)

- Aggregation DSL without raw SQL
- Snowflake / BigQuery connectors
- GraphQL mutations + SQL-endpoint GraphQL
- Git branch browser inside Studio
- dbt model → endpoint helper
- Full browser OIDC login cookies (IdP-hosted + Auth.js) — JWKS Bearer works today

## Not in scope

- Multi-org SaaS control plane / billing
- Managed cloud hosting
- Real-time collaboration

PyPI package name: **`contractapi`** (import `contractapi`).
