# contractapi Studio (`apps/web`)

Next.js UI for designing Postgres → FastAPI contracts.

## Setup

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000/studio

### Auth model

Browser code talks to **Next route handlers** under `/api/studio/*` and `/api/data/*`.

- `/studio/*` requires sign-in at `/login` with the server's `STUDIO_API_KEY` (or SSO when
  Studio OIDC is configured). The key is verified against the backend and kept in an httpOnly,
  `SameSite=Strict` cookie; the handlers forward it — they never inject a key for signed-out users.
- `/api/data/*` (Studio "try it") also requires a signed-in session, then adds `DATA_API_KEY`.
- Cross-site writes (foreign `Origin`) are rejected with 403.
- Local dev only: `STUDIO_DEV_AUTOLOGIN=true` skips the login page (ignored in production builds).

Do **not** put secrets in `NEXT_PUBLIC_*`.

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Next dev server |
| `npm run build` | Production build |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit tests |
| `npx tsc --noEmit` | Typecheck |

## Flow

- `/studio` — catalog
- `/studio/new` — design wizard
- `/studio/[name]` — full editor
- `/studio/diff` — OpenAPI compare
- `/studio/ops` — keys, audit, promote, authenticated exports
