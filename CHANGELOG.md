# Changelog

All notable changes to this project are documented here.

## Unreleased

### API keys for one API, read-only, expiring
- A key now opens only the APIs it was created for (or every API, chosen explicitly, with a
  warning in Studio): another API answers 403. Before, any key opened every API on the server
- A key is "read" (GET only, also over GraphQL) or "read and change"; a read-only key that tries
  to change data gets 403. The old "Permissions" field was stored but never checked
- Keys can expire (401 `key-expired` with the date) and show when they were last used
- Keys & settings asks who the key is for, which APIs, what it may do and when it stops working;
  "Use your API" creates a key for that API only. Key creation is audited with its APIs and access
- Keys made before this change keep working on every API, marked "All APIs" with a hint to
  replace them; a key whose only scope was "read" is now read-only, as its creator asked

### Company login for data APIs
- `jwt.provider: oidc` accepts access tokens from your company login (Keycloak, Azure AD, Okta,
  Google, Auth0…): checked against its public signing keys (JWKS, found from the issuer),
  asymmetric algorithms only, issuer and audience required, keys cached and refreshed on rotation
  (at most one extra fetch per 30 s). `jwt.roles_claim` says where roles are
  (`realm_access.roles`, `groups`, …); they drive endpoint roles and field rules
- Errors say what is wrong: token for another app (audience) or login server (issuer), expired,
  not a login token; an unreachable login server is 503 `auth-unavailable`, never a silent pass
- Studio: "Login tokens" in plain words — this server or your company login — with a
  **Test connection** button (`POST /studio/company-login/test`); "Try it" takes a pasted token
- Example: `backend/examples/company_login.yaml`

### Handing an API to another team
- Each API's OpenAPI now declares its key (API key header or Bearer token), so `/docs` has an
  **Authorize** button and generated clients send it; lists every filter (`status__in`, …),
  `?q=`, `?fields=`, `?format=`; typed response schemas from the real columns; the
  `If-Match` / `Idempotency-Key` headers; and the Problem Details errors each call can return
- Exported OpenAPI, Postman and Python client point at the API's real address
  (`PUBLIC_API_BASE` + `/apis/{name}`). Before, Postman and the client called `/data` (the
  primary API, possibly another one) and Postman's PATCH/PUT/DELETE had no `/:id`
- The Python client covers every allowed operation (create, bulk, update with ETag, delete,
  restore), follows pages (`iter_<name>`), returns a pandas DataFrame (`<name>_dataframe`), raises
  `ApiError` with the Problem Details, and supports JWT APIs
- **Save & make live** lists what would break callers of the live version (removed operations,
  fields, filters, input fields) and asks first; `POST /studio/specs/{name}/compare-draft`.
  Version comparison now also catches removed filters and input fields, and removed fields of
  list endpoints (it only looked at the page wrapper before)

### Safety and governance
- A public API (no key) can no longer allow create/update/delete: refused in the spec, the
  wizard and Settings (anyone reaching the server could change data)
- An id column that is not unique (views, tables without a primary key) can no longer drive
  change/delete by id (one request could change many rows) or next-page links (rows could be
  skipped). The wizard gives such sources page numbers and create-only writes; page-number
  paging sorts by every column, so pages never repeat or skip rows
- Every Studio change is in the audit trail with who made it: make live / stop, save, delete,
  restore, copy to an environment, API keys created / revoked, test tokens. Activity reads the
  log file (it was empty after each restart), names the API of data changes, and shows who /
  what / where / when in plain words (the time column was always "—")
- Copying an API to staging / production keeps the target's own database connection (it used
  to overwrite production's connection with the source's); a first copy says it still uses the
  same database
- Production refuses to start with the demo data key `dev-data-key` or short data keys

### Fixes
- Column types: MySQL `DATETIME`, SQL Server `DATETIME2` / `DATETIMEOFFSET` / `SMALLDATETIME` were
  treated as dates (writes with a time were refused); `TINYINT`, `BIT`, `MEDIUMINT`, `MONEY`
  were treated as text (`true` / numbers refused)
- SQL Server: `?sort=id` with page-number paging answered 500 (the id was in ORDER BY twice)
- Custom SQL endpoints sorted by a non-unique column now add the id as tie-breaker
- Saving an API file with a mistake answered 500; now 400 with the reason
- dbt import reads `schema.yml` as YAML (it wanted JSON), uses the column with dbt's `unique`
  test as the id, makes `/fct-orders`-style paths, and saves the models as a new draft API
- Tools: an empty Git browser says why

### Business rules without code
All of these are spec options and Studio controls (endpoint → Access & rules → Write rules,
Settings → Data format). Defaults keep today's behaviour.
- **Nested writes** (`nested_writes`): create a row together with its `one_to_many` children
  (a customer with their orders) in one transaction; a failing child saves nothing. Children
  cannot choose their parent, and inherit the parent's row-level owner
- **All-or-nothing bulk** (`bulk_atomic`): a bulk create stores every row or none (409/422 with
  the failing index), instead of keeping the valid rows (207)
- **Timestamps** (`timestamps.created_at` / `updated_at`): the API sets them on create and
  update, so `If-Match` on an `updated_at` ETag works even without a database trigger
- **Default and fixed values** (`defaults`, `fixed_values`): defaults fill omitted fields; fixed
  values are always written and cannot be sent by callers (also over GraphQL)
- **Deleted rows**: `soft_delete.restore` adds `POST /{path}/{id}/restore`;
  `soft_delete.reuse_deleted` lets a create reuse the unique value of a deleted row (its email)
  by reviving that row. Never another tenant's row
- **Exact decimals** (`app.decimals: string`): money is returned as `"12.50"` text in REST and
  GraphQL and accepted as text without float rounding. New wizard APIs with decimal columns use it
- **Time zones** (`database.timezone`): date-times stored without a zone (MySQL `DATETIME`, SQL
  Server `datetime2`, Postgres `timestamp`) are returned with their offset; API-set times are
  stored in that zone. New wizard APIs use `UTC`
- **Database changes**: a column or table renamed or dropped under a running API now answers
  `409 schema-changed` with what to do (was a 500). Studio Overview has **Check database
  changes**, also `GET /studio/specs/{name}/database-changes`: missing fields and new columns
- **Snowflake / BigQuery nested data**: `VARIANT`, `OBJECT`, `ARRAY`, `STRUCT`, `RECORD` columns are
  returned as JSON (Snowflake sent JSON text). Listing them as filters, sort fields or writable
  fails activation with a clear message instead of failing per request
- Example: `backend/examples/write_rules.yaml`

### Fixes
- A create or update missing a required (NOT NULL) value answered 409 "already uses one of these
  values" on Postgres/SQL Server and 500 on MySQL; it is now 422 "a required value is missing"
- Any database error reaching the API is a Problem Details answer (some read paths returned a
  plain 500 page)
- Missing Snowflake / BigQuery / DuckDB driver: Problem Details `dependency-missing` (was a 500)
- Studio: "Load tables" no longer reset the draft's database type to Postgres
- One API that could not start (database down, column dropped) took every API on the server down
  after a restart; now only that API answers 503 `api-unavailable` with what to do, and it is
  retried every 15 s, so it recovers by itself once the database is back
- A dropped column in a related table (embedded `orders`) answered 500 "Relation load failed";
  it is now the same 409 `schema-changed` as for the main table
- Embedded related rows used their own number/date format (decimals as floats, no time zone);
  they now follow the API's data format like every other value
- Saving an API file with a mistake answered 500; it is now 400 `invalid-spec` with the reason
- SQL Server: the wizard listed (and pre-ticked) Microsoft's own tables of `master`
  (`spt_values`, `MSreplication_options`, …); system objects are no longer offered
- Wizard: with more than 5 tables nothing is pre-ticked, so a big database is never published
  whole by accident
- GraphQL: fields a caller may not write were silently dropped; they are now refused like in REST

### MySQL and SQL Server
- New database types: **MySQL** (8.x, `pip install 'contractapi[mysql]'`) and **SQL Server**
  (2019/2022, `pip install 'contractapi[sqlserver]'`, no ODBC needed). Every feature works the
  same as on Postgres: tables, filters and `?q=` search, both paging styles, relations,
  create / update / delete, soft delete, bulk, row-level access, custom SQL, aggregates, GraphQL
- `database.driver` is inferred from the URL (`mysql://`, `mssql://`); a driver that does not
  match the URL is rejected with a clear message
- Studio wizard: choose PostgreSQL / MySQL / SQL Server; port, demo login and schema follow
  (MySQL's schema is the database name, SQL Server's is `dbo`). The editor lists both types
- Docker Compose profiles `mysql` and `sqlserver` with demo databases, plus
  `examples/seed_demo.py` (same demo tables on any database) and example contracts
- CI runs the same API tests against real PostgreSQL, MySQL and SQL Server

### Fixes found while testing as a user
- Studio showed SQL Server and MySQL column types with storage details
  (`VARCHAR(200) COLLATE SQL_Latin1_General_CP1_CI_AS`); it now shows `VARCHAR(200)`
- Custom SQL endpoints: get-by-id failed (500) for number ids on Postgres, and for any query
  that has `:params`
- `?sort=` was silently ignored on endpoints with next-page links; it now answers 400 with
  what to change (page-number paging can sort by any allowed field). Studio says so too
- Deleting a row that other rows still refer to answered 500; it is now 409 with an
  explanation. Duplicate-value conflicts explain what happened
- Opening a saved API reset its database type to Postgres in the editor, so saving a DuckDB
  API changed its driver
- GraphQL returned dates and decimals in a different format than REST; both now match
- `?q=` search on number/date columns could miss matches on SQL Server (30-character cast)
- New custom SQL endpoints get a hyphenated address (`/analytics/custom-query`)
- The wizard could replace a name the user had already typed with a suggested `my_api_N`
  when the server answered slowly
- Web fonts load after the page, so a slow or blocked Google Fonts (company firewalls) no
  longer delays Studio pages
- "Database unreachable" shows the driver's own words (e.g. "Access denied for user …",
  "Can't connect to MySQL server on …") instead of raw error codes and byte strings, plus
  what to check next

### Studio redesign
- New look: one design system (Inter / JetBrains Mono, indigo accent) with light and dark mode
  (follows the system, toggle in the sidebar); colours come from shared light/dark tokens
- Sidebar navigation with icons; on phones a top bar and slide-in menu
- My APIs: live/draft counters, cards with a pulsing Live badge and a click-to-copy address
- Wizard: step indicator, table cards with a column picker (private columns locked), access
  choices as cards, a review panel with the final address, and a sticky publish bar
- API page is a workspace with tabs — **Overview** (address, key, code, at a glance),
  **Endpoints** (list + editor side by side), **Settings** and **API file**; the tab is kept in
  the URL (`?tab=endpoints`). "Unsaved changes" shows next to Save draft / Save & make live
- Keys & settings split into API keys, Versions & environments, Downloads and Activity
- In-page confirmation dialogs replace browser pop-ups; short success messages appear as toasts
- Compare versions shows added / changed / removed operations with method badges

### Studio: simpler flow for non-coders
- New-API wizard asks for server, port, database, user and password as separate fields (a
  connection URL is optional), warns before reusing an existing name, and says "Publish API"
- Writes are a single "Also allow adding, changing and deleting rows" switch, off by default,
  with a plain-language warning; new APIs start at version 1.0.0
- API page shows Live / Draft, a success banner after publishing, and Stop / Make live / Delete
- Editor groups rarely-needed options under "Advanced"; labels use plain words
  ("Who can use it?", "Address (URL path)", "Rows per page")
- Navigation: one active item, no horizontal scroll on phones; landing page rewritten

### Fixes
- Signing in from a link on the home page no longer stays stuck on the login page
- "Stop" on an API page stopped every API; it now stops only that one
- Pagination `Link` headers, async-job `Location` and `/apis/<name>/docs` keep the mount prefix
  (`/data` or `/apis/<name>`); cached pages rebuild links per request
- `Accept: text/csv` (and other exports) is never answered from the JSON cache
- "Try it" and its code snippets call the API being edited (`/apis/<name>`), not the primary
  `/data`; `Link`/`Location` headers show the public address instead of the internal host
- Editor "Save & make live" saves first, then activates (no more "undefined" status)
- e2e tests remove the APIs and keys they create

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
