# Changelog

All notable changes to this project are documented here.

## 0.5.0b1 — 2026-10-30 (Beta)

### Packaging
- PyPI name **`dataapi-pg`** (PyPI `dataapi` was taken); import remains `dataapi`
- Classifier **Beta**; docs: STABILITY, SECURITY, COMPATIBILITY, PRODUCTION, UPGRADING, RELEASE

### Reliability
- Persist active APIs under `SPECS_DIR/.runtime/active.json` (+ `DATAAPI_BOOT_SPEC`)
- Webhook retries with backoff + JSONL DLQ
- Durable `insert` job payloads for Redis workers (`dataapi worker`)
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
- **Horizontal job queue**: Redis list + `dataapi worker` when `JOB_QUEUE_ENABLED=true`
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
