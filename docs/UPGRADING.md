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
