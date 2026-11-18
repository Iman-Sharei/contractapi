# Production deploy (single-node Beta)

## Fastest path: Docker Compose

```bash
cp .env.production.example .env
# edit secrets in .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Services: Postgres `:5433`, Redis, API `:8000`, Studio `:3000`.

- Studio → API via internal network; browser hits Studio only.
- Set strong `STUDIO_API_KEY`, `DATA_API_KEYS`, `JWT_SECRET`.

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
