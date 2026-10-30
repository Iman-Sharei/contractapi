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

Forward `X-Forwarded-For` / `X-Forwarded-Proto` so IP allowlists work.

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
