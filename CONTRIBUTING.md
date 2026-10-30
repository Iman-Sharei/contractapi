# Contributing to contractapi

Thanks for helping. Keep changes small, tested, and aligned with **spec-first**
(opt-in endpoints, never mirror the whole schema by default).

## Setup

```bash
# DB
docker compose up -d db

# Backend
cd backend
python -m venv ../.venv && source ../.venv/bin/activate
pip install -e ".[dev]"
export STUDIO_API_KEY=dev-studio-key-change-me
export DATA_API_KEYS=dev-data-key
export JWT_SECRET=dev-jwt-secret-change-me-please-32chars
pytest -q

# Studio UI
cd ../apps/web
cp .env.example .env.local
npm install && npm run dev
```

## Guidelines

1. **Domain stays pure** — no FastAPI imports under `domain/`.
2. **Fail closed** — new fields/endpoints must be allowlisted in the YAML spec.
3. **Errors** — use RFC 9457 `AppError` / problem+json, not ad-hoc JSON.
4. **Tests** — add or extend `backend/tests/` for behavior changes; keep Postgres e2e skippable.
5. **Docs** — update `README.md` / `CHANGELOG.md` for user-visible changes.

## CLI smoke

```bash
contractapi doctor --url postgresql://postgres:postgres@localhost:5433/app
contractapi validate backend/examples/contractapi.yaml
contractapi diff backend/examples/contractapi.yaml backend/examples/jwt_write.yaml
```

## PR checklist

- [ ] `pytest` green
- [ ] `npx tsc --noEmit` in `apps/web` if UI changed
- [ ] No secrets committed (`.env`, real API keys)
- [ ] CHANGELOG entry under Unreleased or next version
