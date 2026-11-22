# Production deploy (single-node Beta)

## Fastest path: Docker Compose

```bash
cp .env.production.example .env
# edit secrets in .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Services: Postgres `:5433`, Redis, API `:8000`, Studio `:3000`.

- Studio → API via internal network; browser hits Studio only.
- Set strong `STUDIO_API_KEY`, `DATA_API_KEYS` (or leave it empty and create keys in Studio),
  `JWT_SECRET`. With `ENVIRONMENT=production` the API refuses to start with default or short
  values, including the demo data key `dev-data-key`.
- Set `NEXT_PUBLIC_API_BASE` (web) and `PUBLIC_API_BASE` (API) to the address callers use, e.g.
  `https://api.example.com`. Studio shows it in code samples, and the exported OpenAPI, Postman
  collection and Python client point there, so they work for other teams as downloaded.

## Reverse proxy (TLS)

Terminate TLS at Caddy/Nginx/Traefik:

- `https://studio.example.com` → `web:3000`
- `https://api.example.com` → `api:8000` (data-plane + studio API if needed)

Forward `X-Forwarded-For` / `X-Forwarded-Proto`, and set `TRUSTED_PROXIES` on the API to the
proxy's IPs/CIDRs (e.g. `TRUSTED_PROXIES=10.0.0.0/8`). The API only honors `X-Forwarded-For` from
those addresses, so clients cannot spoof their IP past `ip_allowlist`.

### Studio sign-in behind a proxy

- Users sign in at `https://studio.example.com/login` with `STUDIO_API_KEY` (or SSO).
- **SSO (OIDC):** register the redirect URI **on the Studio origin** —
  `https://studio.example.com/api/studio/oidc/callback` — and set
  `STUDIO_OIDC_REDIRECT_URI` to the same value plus `STUDIO_OIDC_POST_LOGIN_URL=https://studio.example.com`.
  The login cookies then belong to the Studio site even when the API lives on another domain.
- Set `STUDIO_OIDC_CLIENT_ID` (or `STUDIO_OIDC_AUDIENCE`); the IdP client must allow PKCE (S256).
- Without Redis, cache / rate limits / idempotency / jobs are per process: run one API worker,
  or set `REDIS_URL` before scaling out.

## Company login for data APIs (OIDC)

For APIs whose callers sign in with the company identity provider, set "Who can use it?" to
login tokens and choose **Your company login** (or `jwt.provider: oidc` in YAML):

- **Issuer**: exactly the `iss` of the tokens (Keycloak `https://host/realms/<realm>`, Azure AD
  `https://login.microsoftonline.com/<tenant>/v2.0`, Okta `https://<org>.okta.com/oauth2/default`).
  The API reads `<issuer>/.well-known/openid-configuration` and the signing keys it points to,
  so the API server must reach the login server (https; http only for local test servers).
- **Audience**: the client ID / API identifier your login server puts in `aud`.
- **Roles**: where the roles are (`realm_access.roles`, `roles`, `groups`); endpoint roles and
  field rules use them. Use **Test connection** in Studio before making the API live.
- Needs `pip install 'contractapi[oidc]'` (the Docker image includes it).

## API keys

Create one key per app or person in Studio → Keys & settings, for only the APIs it needs, read
only unless it must change data, with an expiry. `DATA_API_KEYS` are server-wide operator keys
(every API, read and write): keep them out of apps.

## Pip-only (API without Studio UI)

```bash
python -m venv .venv && source .venv/bin/activate
pip install 'contractapi[redis]'
export STUDIO_API_KEY=... DATA_API_KEYS=... JWT_SECRET=... REDIS_URL=redis://127.0.0.1:6379/0
contractapi serve --host 0.0.0.0 --port 8000
```

Activate a YAML via Studio HTTP or bake a startup spec (see `DATAAPI_BOOT_SPEC`).

## Multi-replica notes (Beta limits)

| Concern | Guidance |
|---------|----------|
| Active spec | Persisted under `SPECS_DIR/.runtime/`; each replica should share the volume **or** activate via API against each instance |
| Jobs | Set `JOB_QUEUE_ENABLED=true` + run `contractapi worker` on ≥1 worker; API nodes enqueue only |
| Cache / idempotency / JWT revoke | Requires Redis |
| Sticky sessions | Not required for data-plane if Redis is shared |

True multi-region / multi-tenant SaaS is **out of scope**.

## Health

- `GET /health` — liveness
- `GET /ready` — DB check when a spec is active
- `GET /data/metrics` — Prometheus text when data API is up
