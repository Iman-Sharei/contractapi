# Upgrading

## 0.6.1 → next

No YAML changes are required: every new option is off by default. Behaviour changes to check:

1. **Missing required value → 422** (was 409 on Postgres/SQL Server, 500 on MySQL). Clients that
   treated 409 as "duplicate" now get 409 only for duplicates and missing referenced rows.
2. **Schema changes → 409 `schema-changed`** (was 500) when a column/table the API uses is gone.
3. **Snowflake / BigQuery:** a `VARIANT`/`OBJECT`/`ARRAY`/`STRUCT`/`RECORD` column listed in
   `filters`, `sortable` or `writable_fields` now stops activation with a message (it failed per
   request before). Remove it from those lists. Such columns are now returned as JSON, not text.
4. **`fixed_values` / `timestamps` columns** are removed from what clients may send: a client
   value for them is a 422.
5. **Public APIs are read-only.** A spec with `auth: none` and write methods no longer loads: choose
   `api_key` / `jwt`, or remove the write methods.
6. **Ids that are not unique.** A table endpoint whose `primary_key` is not the table's primary key
   or a unique column no longer starts with PATCH / PUT / DELETE, or with cursor paging (use
   `pagination.mode: offset`). Views with cursor paging still start, with a warning in the log.
7. **`ENVIRONMENT=production`** refuses `DATA_API_KEYS` with `dev-data-key` or keys under 16 chars.
8. Set **`PUBLIC_API_BASE`** on the API (same value as the web's `NEXT_PUBLIC_API_BASE`) so the
   exported OpenAPI / Postman / Python client point at the right address.
9. **API keys:** existing keys keep working on every API (shown as "All APIs" in Studio, with a
   hint to replace them). A key created with only the `read` scope is now read-only. New keys:
   `POST /studio/keys` needs `apis` (saved API names or `["*"]`); `access` defaults to `read`.
   Older scripts that send `scopes` still work.
10. **Login tokens:** `jwt.algorithm` other than HS256/384/512 now requires `jwt.provider: oidc`
   (tokens from a login server; it never worked with this server's secret). With `oidc`,
   `/auth/refresh` and `/auth/revoke` are not offered: the login server handles those.

## 0.6.0 → 0.6.1

1. **Sign in once more:** Studio session cookies changed format (signed token instead of the key).
2. **Optional:** set `STUDIO_SESSION_SECRET` on the Studio (web) server to sign sessions with a
   dedicated secret; rotating it (or `STUDIO_API_KEY`) signs everyone out.
3. **Optional:** set `SECRETS_ENCRYPTION_KEY` on the API (and workers) to encrypt the secret store;
   needs the `cryptography` package (`contractapi[oidc]`). Keep the key outside `SPECS_DIR` and back it up —
   encrypted secrets cannot be read without it.
4. **SSO behind a proxy:** you can now register `https://<studio>/api/studio/oidc/callback` as the
   redirect URI (see `docs/PRODUCTION.md`).

## 0.5.x → 0.6.0

1. **Studio sign-in:** open `/login` and paste the server's `STUDIO_API_KEY` (or use SSO).
   For local `npm run dev`, set `STUDIO_DEV_AUTOLOGIN=true` in `apps/web/.env.local`.
2. **`POST /auth/token` removed** from data APIs. Get tokens from your IdP; for testing use
   `POST /studio/token {"sub", "roles", "api", "claims"}`.
3. **GraphQL:** drop the `claims:` argument — send a Bearer JWT (or API key) instead. `roles:`
   still works but only narrows to roles already in the token.
4. **`auth: api_key`** now needs at least one key (`DATA_API_KEYS` or Studio → Ops → API keys);
   use `auth: none` for an intentionally public read-only API.
5. **`ENVIRONMENT=production`** refuses to boot with default/short `STUDIO_API_KEY` / `JWT_SECRET`.
6. **Endpoint paths:** must be lowercase letters, digits, `-`, `_` (e.g. `/order-items`). With an
   empty `api_prefix`, a path cannot start with `health`, `ready`, `metrics`, `docs`, `redoc`,
   `auth`, `jobs` or `graphql` — rename (e.g. `/metrics-data`) or set `api_prefix: /v1`.
   Saved specs that break this rule fail validation with a message saying how to fix them.
7. **PUT** now replaces the whole resource and requires every writable field (422 lists the
   missing ones). Use **PATCH** for partial updates.
8. **Secrets:** the next save/activate moves a literal DB password (and webhook secrets) into
   `SPECS_DIR/.secrets/` and rewrites the spec to `${secret:db-<name>}`. Back up / mount that
   folder with your specs. Workers on other hosts need the same folder or `${env:VAR}` refs.
9. **Behind a reverse proxy** with `ip_allowlist`: set `TRUSTED_PROXIES` (IPs/CIDRs of the proxy),
   otherwise the proxy's own address is checked.
10. **Git browser:** the `repo` query parameter is gone; set `GIT_REPO_PATH` on the server.
11. **Filters/sort with RBAC:** callers can only filter/sort on fields their role can see.
12. **Studio OIDC:** set `STUDIO_OIDC_CLIENT_ID` (or `STUDIO_OIDC_AUDIENCE`) whenever
    `STUDIO_OIDC_ISSUER` is set — otherwise the server will not start. Your IdP client must allow
    PKCE (S256); public clients no longer need a client secret.
13. **Webhooks to internal services** (e.g. `http://my-service:8080` in Docker): set
    `WEBHOOK_ALLOW_PRIVATE=true`. Receivers that answer with a redirect must be called at their
    final URL.
14. **Idempotency:** a second request with the same `Idempotency-Key` while the first is still
    running now gets `409 idempotency-in-progress` — retry after a moment.
15. **`api_prefix` default:** a YAML spec without `app.api_prefix` still serves under `/v1`; the
    Studio wizard writes an empty prefix explicitly (URLs like `/customers`). Nothing changes for
    existing specs.

## 0.4.x → 0.5.0

1. **PyPI name:** install `contractapi`. Import is `import contractapi`.
2. **Studio env:** move secrets to server-only `STUDIO_API_KEY` / `DATA_API_KEY` (see `apps/web/.env.example`).
3. **Activate persistence:** active APIs are restored from `SPECS_DIR/.runtime/active.json` on boot.
4. **Webhooks:** failed deliveries retry with backoff; exhausted events land in `SPECS_DIR/.runtime/webhook-dlq.jsonl`.
5. **Experimental flags:** `CONTRACTAPI_EXPERIMENTAL` is reserved for future opt-ins. **OIDC**, **queue**, **multi_active**, **Parquet**, **DuckDB**, and **GraphQL** are GA — configure extras / env only; legacy experimental tokens are ignored.
6. **API prefix:** Studio wizard default is empty (no `/v1`). Existing specs keep their stored prefix.
7. **Multi-active:** `/apis/{name}` is always mounted. Use Studio “Mount /apis” or `POST /studio/activate/{name}` for secondary APIs.

### YAML

No required field renames in 0.5.0. New optional fields: `parquet_export`, `database.driver`, `app.jwt` tunables already present.
