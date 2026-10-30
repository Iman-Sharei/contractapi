# Compatibility matrix

| Component | Supported |
|-----------|-----------|
| Python | **3.10, 3.11, 3.12** (3.13 best-effort) |
| PostgreSQL | **14–16** (tests on 16) |
| Redis | **6+** optional (cache, idempotency, jobs) |
| Node.js (Studio) | **20 LTS** |
| Next.js Studio | 15.x as shipped in `apps/web` |

## Optional extras

| Extra | Package |
|-------|---------|
| `pip install 'dataapi-pg[redis]'` | shared KV / queue |
| `pip install 'dataapi-pg[parquet]'` | Parquet export |
| `pip install 'dataapi-pg[duckdb]'` | DuckDB driver |
| `pip install 'dataapi-pg[graphql]'` | `/graphql` |
| `pip install 'dataapi-pg[oidc]'` | cryptography for OIDC |
| `pip install 'dataapi-pg[all]'` | everything |

Import name remains **`dataapi`**; PyPI distribution name is **`dataapi-pg`** (`dataapi` was already taken on PyPI).
