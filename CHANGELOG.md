# Changelog

All notable changes to this project are documented here.

## 0.5.0 — 2026-11-10 (Beta)

### Deploy / hardening
- Web Docker build: drop Turbopack + `next/font/google` (runtime CSS fonts) so images build offline
- CSS Modules purity: move global focus styles to `globals.css`
- API image installs GA extras (parquet/duckdb/graphql/oidc) + git; mount workspace for git browser
- Filters accept soft alias `field_op` (e.g. `name_contains`) alongside `field__op`
- List `include`/`expand` reserved for relation embedding (`include=none` skips)
- Activate responses include `name` / `mount` / `primary`
- Scenario matrix: `scripts/deploy_scenario_matrix.sh`; Playwright e2e uses Compose DB host `db`

### Studio
- Three-step wizard: Connect → Pick tables/columns → Guards & publish
- Default API prefix empty (URLs without `/v1`)
- Editor form layout rebuilt (connection / surface / toggles)
- Relations editor: type, keys, max_per_parent, field pickers; many-to-one from parent FKs
- Security tab: FieldValidation rules, multi-webhook events, JWT config, RBAC field matrix
- Docker Compose Redis no longer binds host `:6379` (avoids local clashes)

### Runtime
- **Parquet export is GA** — no `CONTRACTAPI_EXPERIMENTAL=parquet` gate; still needs `pyarrow`
- **DuckDB driver is GA** — no experimental gate; Studio Driver selector + SQL preview; still needs `duckdb` extra
- **GraphQL read facade is GA** — mounts `/graphql` when `strawberry` is installed; no experimental gate
- **OIDC / Redis queue / multi-active are GA** — no experimental gates; Studio catalog shows live mounts + Mount /apis
- `CONTRACTAPI_EXPERIMENTAL` default empty (legacy `all` is a no-op)
- **GraphQL:** SQL endpoint reads + `createItem` / `updateItem` / `deleteItem` mutations for allowlisted table methods
- **GraphQL:** nested `relations` on reads + `roles` arg for RBAC field allowlists
- **Aggregation DSL:** `aggregate:` (group_by + count/sum/avg/min/max) compiles to SQL; Studio SQL tab editor + example
- **Aggregation DSL richer:** `where` / `having` / `windows` (row_number, rank, sum/avg/count)
- **Snowflake + BigQuery drivers** (optional extras) + Studio driver selector + examples
- **GraphQL:** row-level `claims` arg (REST RLS parity) + poll-based `endpointStream` subscription
- **dbt import:** `POST /studio/import/dbt` (schema.yml or manifest.json → endpoint drafts)
- **Git browser:** `/studio/git/*` + Studio Tools page
- **OIDC cookie BFF:** `/studio/oidc/{login,callback,logout,me}` (+ client_id / redirect_uri env)

### Quality
- Backend e2e: activate with empty prefix → `GET /data/customers`
- Playwright smoke: Studio wizard → Activate → data plane
- CI job `e2e` runs Postgres + API + Studio + Playwright

## 0.5.0b1 — 2026-10-30 (Beta)

### Packaging
- PyPI name **`contractapi`** (legacy name `dataapi` was taken on PyPI); import remains `contractapi`
- Classifier **Beta**; docs: STABILITY, SECURITY, COMPATIBILITY, PRODUCTION, UPGRADING, RELEASE

### Reliability
- Persist active APIs under `SPECS_DIR/.runtime/active.json` (+ `DATAAPI_BOOT_SPEC`)
- Webhook retries with backoff + JSONL DLQ
- Durable `insert` job payloads for Redis workers (`contractapi worker`)
- `DATAAPI_EXPERIMENTAL` feature gate

### Ops
- Full Compose stack: Postgres + Redis + API + Studio (+ optional worker profile)
- CI: Python 3.10–3.12 matrix + web Vitest/typecheck + wheel `twine check`
- E2E smoke: introspect → save → activate → GET /data

## 0.4.0 — 2026-10-30

### Added
- **Parquet** list export (`parquet_export`, `?format=parquet`) via optional `pyarrow`
- **Studio OIDC** (JWKS) alongside `X-API-Key` break-glass — Keycloak/Authentik/Okta-ready
- **Multi-active specs**: primary `/data` + named mounts `/apis/{name}`; `GET /studio/active/list`
- **Horizontal job queue**: Redis list + `contractapi worker` when `JOB_QUEUE_ENABLED=true`
- **DuckDB** warehouse driver (`database.driver: duckdb`) for local/analytics SQL
- **GraphQL facade** at `/graphql` when `strawberry` is installed (contract-scoped reads)

### Studio UI (P0–P2 hardening)
- Next.js **BFF** (`/api/studio`, `/api/data`) — Studio/data keys stay server-side
- Authenticated Postman / SDK / OpenAPI downloads; catalog error≠empty; Vitest suite
- Schema-qualified tables, server dump-yaml rail, confirms, copy, audit table, a11y basics

### Docs
- Examples: `duckdb_local.yaml`, `oidc_studio.env.example`; PRODUCT_GAPS updated

## 0.3.0 — 2026-10-30

### Added
- Studio product flow: catalog, wizard, detail, OpenAPI diff, Ops
- SQL endpoints with typed named params, `?q=` search, NDJSON export
- Soft-delete, ETag/If-Match, row-level security, bulk + async 202 jobs
- API-key CRUD, IP allowlist, write webhooks (HMAC), audit viewer API
- Spec snapshots on save, env promote, Postman + Python SDK export
- OTel-lite spans, Helm chart skeleton, richer CLI (`init`, `diff`, `doctor`, `serve`)

### Changed
- Default API prefix `/v1`; example demo DB on port **5433**

## 0.2.0

- JWT/RBAC, cursor pagination, relations, cache, idempotency, metrics

## 0.1.0

- Initial spec-first Postgres → FastAPI + Studio MVP
