# Remaining gaps (post-Beta)

**Maturity:** Beta `0.5.0b1` — see [STABILITY.md](STABILITY.md).

## Experimental (enabled via `DATAAPI_EXPERIMENTAL`)

| Feature | Flag |
|---------|------|
| GraphQL facade | `graphql` |
| DuckDB driver | `duckdb` |
| Parquet export | `parquet` |
| Studio OIDC | `oidc` |
| Redis job queue | `queue` |
| Multi-active `/apis/{name}` | `multi_active` |

Default: `all`.

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

PyPI package name: **`dataapi-pg`** (import still `dataapi`).
