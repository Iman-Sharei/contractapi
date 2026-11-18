# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.5.x (Beta) | Yes — security fixes |
| < 0.5 | Best-effort only |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security bugs.

Email the maintainer listed on the GitHub profile / PyPI project page with:

- Affected version (`contractapi version`)
- Description + impact
- Minimal reproduction (no real secrets)

We aim to acknowledge within **72 hours** and ship a fix or mitigation advisory for Beta.

## Threat model (self-hosted)

**Trust boundary:** operators control the host, Postgres, Redis, and Studio BFF env.

| Asset | Risk if compromised |
|-------|---------------------|
| `STUDIO_API_KEY` / Studio OIDC | Full control-plane (activate, keys, promote) |
| `DATA_API_KEYS` / JWT secret | Data-plane read/write per contract |
| Database URL in YAML | Direct DB access |
| Webhook secrets | Spoofed event delivery |

**Assumptions:** TLS terminated at reverse proxy; Studio not exposed to the public internet without auth; demo keys never used in production.

## Hardening checklist

1. Change all default keys (`STUDIO_API_KEY`, `DATA_API_KEYS`, `JWT_SECRET`). With
   `ENVIRONMENT=production` the server refuses to start on default/short secrets.
   `auth: api_key` with no configured keys rejects every request (fail closed).
   Data-plane JWTs come from your IdP; there is no public token endpoint (test tokens:
   admin-only `POST /studio/token`). GraphQL authorization uses only the verified token.
2. Prefer Studio behind VPN / SSO (OIDC) + keep API key as break-glass only.
3. Use Next BFF (`STUDIO_API_KEY` server-only) — never `NEXT_PUBLIC_*` secrets in prod.
4. Set `app.read_only: true` unless writes are required; enable `row_level` + RBAC for JWT.
5. Restrict `ip_allowlist` when exposing data-plane; behind a reverse proxy set
   `TRUSTED_PROXIES` so `X-Forwarded-For` is honored only from it.
   DB passwords/webhook secrets live in `SPECS_DIR/.secrets` (0600) — protect and back up that folder.
6. Put Redis on a private network; enable `JOB_QUEUE_ENABLED` only if you run workers you trust.
7. Rotate managed API keys via Studio Ops; revoke on leak.
8. Keep `audit_enabled` and ship `AUDIT_LOG_PATH` off-box.

## Known limitations (Beta)

- Webhook delivery is best-effort with retries; not a transactional outbox.
- Horizontal workers require Redis; job payloads are JSON (no arbitrary pickle).
- OIDC validates JWKS tokens; full browser login UX still relies on your IdP + BFF cookies (optional).
