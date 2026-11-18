# Upgrading

## 0.5.0 → next (security fixes)

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
