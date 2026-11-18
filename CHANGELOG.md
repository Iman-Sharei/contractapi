# Changelog

All notable changes to this project are documented here.

## 0.6.1 — 2026-11-19 (Beta)

### Fixes
- `examples/duckdb_local.yaml` did not parse; CI now loads every example
- Studio YAML preview could produce invalid YAML (unquoted URLs/SQL) and dropped some fields;
  it now uses a generic emitter that quotes what YAML would misread and round-trips through the API
- Play tab can send JWT claims, so row-level security is testable from the UI
- SSO callbacks routed through the Studio origin work (OIDC state cookie is forwarded)

### Security
- Studio session cookie is a signed, expiring token (HMAC of `STUDIO_SESSION_SECRET`, or derived
  from `STUDIO_API_KEY`); it never contains the key. Rotating either secret signs everyone out
- Webhooks connect to the exact IP that passed the SSRF check (closes DNS rebinding); TLS still
  verifies the hostname
- Optional `SECRETS_ENCRYPTION_KEY`: AES-256-GCM encryption of the secret store at rest;
  existing plaintext entries are re-encrypted on first read

### Internal
- Large modules split (largest ~350 lines); public import paths unchanged
- Agent rules tracked: `.claude/` is the source, `scripts/sync_agent_rules.py` generates `.cursor/rules`

## 0.6.0 — 2026-11-18 (Beta)

Security-hardening and usability release. **Breaking changes** — read
[docs/UPGRADING.md](docs/UPGRADING.md) before upgrading.

### Studio UX
- "Use your API" panel after activation: live URL, one-click API key, runnable curl / Python / pandas
- Plain-language safety checklist in the wizard, the Security tab and the API page
- Inline URL-path errors; wizard generates valid paths; relation editor can hide deleted rows

### Internal
- Studio editor split into a state hook and tab components; data-plane builder split into the
  `application/data_api/` package; Aggregate DSL in `domain/models/aggregate.py`
- CI lints backend (ruff) and web (eslint), tests GA extras, runs wizard + editor e2e
- Single version source (`contractapi.__version__`); `X-Trace-Id` validated; API names validated on activate

### Hardening (Medium)
- OIDC browser login uses PKCE (S256) and a nonce; tokens must be issued for this Studio
  (`STUDIO_OIDC_AUDIENCE`, or `aud`/`azp` = `STUDIO_OIDC_CLIENT_ID`); the server refuses to start
  with an issuer but neither; `return_to` can no longer redirect off-site
- Webhooks refuse private/loopback/link-local/metadata targets (opt in: `WEBHOOK_ALLOW_PRIVATE=true`),
  do not follow redirects, and blocked deliveries go straight to the DLQ
- Postgres SQL endpoints run in a `READ ONLY` transaction (side-effecting functions cannot write)
- Relations cap rows per parent in SQL (`ROW_NUMBER`) and can hide deleted children
  (`soft_delete_column`, also in the Studio relation editor)
- Body-size limit counts received bytes (chunked requests included)
- Idempotency keys are claimed atomically: a concurrent duplicate gets 409 instead of a second write;
  a failed request releases the key so it can be retried
- In-memory store is capped (`MEMORY_KV_MAX_ENTRIES`, default 10000); in-process job registry bounded
- `/jobs/{id}` only answers the caller that created the job (others get 404)
- Studio DB errors stay actionable but never include credentials; data-plane relation errors no
  longer echo driver messages; OpenAPI export errors are Problem Details
- GraphQL resolvers run in a worker thread (no event-loop blocking)

### Correctness & API standards
- Filters convert values to the column type: numeric, date, datetime, bool and uuid columns
  now filter correctly (were HTTP 500). A bad value is a 400 that says what format is expected;
  `?q=` searches text columns only; `%`/`_` in `contains`/`startswith` are literal
- SQL endpoints: bad `sql_params` → 422, bad filter values → 400 (were 500)
- `PUT` is a real replace (missing writable fields → 422); `PATCH` stays partial
- `201 Created` includes a `Location` header; write bodies are documented in OpenAPI
- GET `ETag` now works with `If-Match` on PATCH/PUT/DELETE even with relations/RBAC/sparse fields
- Offset paging always ends with the primary key as tie-breaker (stable pages)
- CORS allows `If-Match`/`If-None-Match` and exposes `ETag`, `Link`, `Location`, rate-limit headers
- URL paths are validated (lowercase, digits, `-`, `_`); without an API prefix, paths cannot
  shadow built-in routes (`/health`, `/metrics`, `/docs`, `/jobs`, …). Studio explains bad paths
  inline and the wizard generates valid ones

### Security
- RBAC field allowlists apply to POST/PATCH/PUT/bulk responses; filters, `?q=` and sort only
  accept fields the caller may see; endpoint `roles` are enforced on writes (were GET-only)
- Database passwords and webhook secrets are moved from specs into a server-side secret store
  (`SPECS_DIR/.secrets`, 0600) on save/activate; YAML keeps `${secret:NAME}` (or `${env:NAME}`).
  Studio responses mask any literal password
- IP allowlist: real CIDR matching; `X-Forwarded-For` only trusted from `TRUSTED_PROXIES`
- Git browser: only `GIT_REPO_PATH`; option-like refs/paths rejected (was arbitrary file write)
- Anonymous rate limiting is per client IP instead of one shared bucket

### Performance
- Data-plane handlers run in the threadpool (no event-loop blocking); API rebuilds too
- Pooled Postgres engines are shared per URL; one-off checks use no pool (no connection leaks)

### Security (breaking — see docs/UPGRADING.md)
- Studio web requires sign-in (`/login`, Studio key or SSO); the Next BFF no longer injects
  `STUDIO_API_KEY` / `DATA_API_KEY` for signed-out browsers, and blocks cross-site writes
- Removed the unauthenticated data-plane `POST /auth/token`; extra claims can no longer
  override `sub`/`roles`/`exp`/`iss`/`aud`/`jti`/`typ`. `POST /studio/token` now uses the target
  API's `jwt` config and accepts test `claims`
- GraphQL: roles/row-level come from the verified token only (`claims` argument removed;
  `roles` can only narrow); endpoint `roles`, row-level, validations, audit, webhooks and cache
  invalidation now apply to mutations; WebSocket subscriptions are authenticated
- Response cache and idempotency keys are scoped per API contract and per row-level tenant/caller
- `auth: api_key` with zero configured keys now returns 401 (was: open); API-key principals no
  longer embed part of the key; production boot refuses default secrets

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
