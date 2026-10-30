# dataapi

[![CI](https://img.shields.io/badge/CI-pytest-0B6E4F)](.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB)](backend/pyproject.toml)

**Spec-first Postgres → FastAPI**, with a Next.js Studio.

**Maturity: Beta (`0.5.0b1`)** — see [docs/STABILITY.md](docs/STABILITY.md).  
PyPI: `pip install dataapi-pg` (import name still `dataapi`).

You design the API contract. The database is only the source — never the public surface.

```
PostgreSQL / DuckDB ──introspect──► Studio / YAML ──activate──► FastAPI /data + /apis/{name}
                                                              (+ OpenAPI, optional /graphql)
```

## Why not just PostgREST / Hasura?

| Tool | Typical gap | dataapi |
|---|---|---|
| PostgREST / Hasura / Directus | API ≈ full schema | Opt-in endpoints + custom paths |
| sandman2 / db2api | Auto-expose tables | Field allowlists; read-only default |
| fastapi-forge | Generates a zip | Runtime from versionable YAML |

Security baselines: **OWASP API Top 10**, **RFC 9457**, **Zalando API guidelines**.

## 5-minute start

```bash
# One-command local stack (API + Studio + Postgres + Redis)
docker compose up -d --build
# Studio http://localhost:3000  · API http://localhost:8000/docs
```

Or pip + Studio separately:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "./backend[dev]"
export STUDIO_API_KEY=dev-studio-key-change-me DATA_API_KEYS=dev-data-key
export JWT_SECRET=dev-jwt-secret-change-me-please-32chars CORS_ORIGINS=http://localhost:3000
dataapi serve --host 127.0.0.1 --port 8000
# other terminal:
cd apps/web && cp .env.example .env.local && npm install && npm run dev
```

Production notes: [docs/PRODUCTION.md](docs/PRODUCTION.md) · Security: [docs/SECURITY.md](docs/SECURITY.md).

### Call the data plane (after Activate in Studio)

```bash
curl -sS -H "X-API-Key: dev-data-key" \
  "http://127.0.0.1:8000/data/v1/customers?limit=5" | jq .

# pandas
python - <<'PY'
import httpx, pandas as pd
r = httpx.get(
    "http://127.0.0.1:8000/data/v1/customers",
    headers={"X-API-Key": "dev-data-key"},
    params={"limit": 5},
)
r.raise_for_status()
print(pd.DataFrame(r.json()["items"]))
PY
```

## Studio flow

| Route | Purpose |
|---|---|
| `/studio` | My APIs — list / activate / deactivate / delete |
| `/studio/new` | Wizard — Connect → Sources → Shape → Guards → Review |
| `/studio/[name]` | Full contract editor + try-it |
| `/studio/diff` | OpenAPI diff between saved specs |
| `/studio/ops` | API keys, audit, promote, Postman/SDK |

## CLI

```bash
dataapi version
dataapi doctor --url postgresql://postgres:postgres@localhost:5433/app
dataapi init my.yaml --template readonly   # readonly|jwt|sql|webhooks
dataapi introspect -u postgresql://postgres:postgres@localhost:5433/app
dataapi validate backend/examples/dataapi.yaml
dataapi diff backend/examples/dataapi.yaml backend/examples/jwt_write.yaml --fail-on-breaking
dataapi serve                              # studio + /data
dataapi serve backend/examples/sql_metrics.yaml --data-only
```

## Examples

| File | Shows |
|---|---|
| [backend/examples/dataapi.yaml](backend/examples/dataapi.yaml) | Read-only, relations, cursor, soft-delete, ETag |
| [backend/examples/jwt_write.yaml](backend/examples/jwt_write.yaml) | JWT roles, writes, validations, bulk |
| [backend/examples/sql_metrics.yaml](backend/examples/sql_metrics.yaml) | SQL metrics + CSV/NDJSON/Parquet |
| [backend/examples/webhooks.yaml](backend/examples/webhooks.yaml) | Write webhooks with HMAC |
| [backend/examples/duckdb_local.yaml](backend/examples/duckdb_local.yaml) | DuckDB warehouse driver MVP |
| [backend/examples/oidc_studio.env.example](backend/examples/oidc_studio.env.example) | Studio OIDC + Redis job queue env |

## What you get

- Opt-in tables/views/SQL · sensitive column block · read-only default  
- API key / JWT (+ refresh/revoke) · Studio OIDC (optional) · row-level · soft-delete · ETag  
- Filters / `?q=` / sparse fields · cursor|offset · CSV/NDJSON/Parquet · Link headers  
- Idempotency · cache · bulk · async 202 (in-process or Redis queue + `dataapi worker`)  
- Multi-active mounts `/data` + `/apis/{name}` · optional `/graphql` · audit JSONL  
- Prometheus `/metrics` · `X-Trace-Id` · optional Redis KV · Helm skeleton  

## Limits (honest)

- Beta — experimental flags for GraphQL / DuckDB / Parquet / OIDC / queue / multi-active  
- Warehouse beyond **Postgres + DuckDB** (Snowflake/BQ) still future  
- Multi-active ≠ multi-org SaaS control plane  

More: [docs/PRODUCT_GAPS.md](docs/PRODUCT_GAPS.md) · [docs/UPGRADING.md](docs/UPGRADING.md).

## Layout

```
dataapi/
├── apps/web/                 # Next.js Studio
├── backend/                  # Python package + CLI
│   ├── examples/             # YAML templates
│   └── src/dataapi/
├── deploy/helm/dataapi/      # Kubernetes chart
├── docker-compose.yml        # Demo Postgres :5433
└── docs/
```

## Tests & contribute

```bash
cd backend && pytest -q
cd apps/web && npm test && npm run typecheck
```

See **[Contributing](CONTRIBUTING.md)** and **[Changelog](CHANGELOG.md)**.

## License

MIT — see **[LICENSE](LICENSE)**.
