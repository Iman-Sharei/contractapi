# dataapi Studio (`apps/web`)

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
Those handlers inject `STUDIO_API_KEY` / `DATA_API_KEY` from **server** env.
Do **not** put secrets in `NEXT_PUBLIC_*` for production.

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
