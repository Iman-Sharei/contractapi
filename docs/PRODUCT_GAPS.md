# Remaining gaps (post-Beta)

**Maturity:** Beta `0.5.0` — see [STABILITY.md](STABILITY.md).

## Experimental

No features currently require `CONTRACTAPI_EXPERIMENTAL`. The env var remains for future opt-ins; `all` / legacy tokens are ignored.

## GA (config / optional extras only)

| Feature | Enable with |
|---------|-------------|
| Parquet list export | `pip install 'contractapi[parquet]'` + `parquet_export: true` |
| DuckDB driver | `pip install 'contractapi[duckdb]'` + `database.driver: duckdb` |
| GraphQL read facade | `pip install 'contractapi[graphql]'` → `/graphql` |
| Studio OIDC (JWKS) | `STUDIO_OIDC_ISSUER` (+ optional audience / JWKS / email allowlist) |
| Redis job queue | `JOB_QUEUE_ENABLED=true` + `REDIS_URL` (+ `contractapi worker`) |
| Multi-active mounts | Always on: primary `/data` + `/apis/{name}` |

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
