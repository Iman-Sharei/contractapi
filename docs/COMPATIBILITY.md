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
| `pip install 'contractapi[redis]'` | shared KV / queue |
| `pip install 'contractapi[parquet]'` | Parquet export |
| `pip install 'contractapi[duckdb]'` | DuckDB driver |
| `pip install 'contractapi[graphql]'` | `/graphql` |
| `pip install 'contractapi[oidc]'` | cryptography for OIDC |
| `pip install 'contractapi[all]'` | everything |

Import name remains **`contractapi`**; PyPI distribution name is **`contractapi`** (`contractapi` was already taken on PyPI).
