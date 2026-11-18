---
name: verify-task
description: "Verify the previous contractapi task end-to-end (spec model, services, HTTP, Studio UI) with the demo Postgres and fix failures until all checks pass. Manual attach only."
---

# Verify Previous Task

Verify the **last implemented task**. Do not redesign it. Validate it end-to-end and fix failures.

## Workflow

1. Inspect the task: `git diff`, `git status`, the user's request.
2. Map the flow it touches:
   `Studio UI → Next BFF (/api/*) → /studio route → application service → ApiSpec (domain) → activate`
   and/or
   `HTTP request → data-plane guards (auth, IP, rate limit) → generated route → filters/RLS/RBAC → DB → response`
3. List every branch: auth, role/RBAC, row-level, validation (spec + payload), not found, conflict,
   idempotency, ETag, cache, async job, webhooks, audit.
4. Follow existing conventions (`.claude/rules/`): Problem Details errors, logic in `application/`,
   `audit_event` for writes, spec options exposed in Studio.

## Sample Data

Use the demo Postgres (`docker compose up -d db`, port 5433). Create an isolated schema per test
(see `tests/test_product_completeness.py`) and drop it afterwards. Cover positive and negative cases.

## Verify

### Domain (`domain/models/*`)
- invalid specs are rejected with an actionable message (path rules, fields ⊂ table, RBAC fields)
- YAML round-trip: `parse_spec(yaml.safe_load(dump_spec(spec)))` equals the input

### Application / data plane
- typed filters (numbers, dates, bools, `in`), sort and `?q=`; bad values → 400, never 500
- writes: role gate, RBAC projection of the response, row-level injection, validations,
  idempotency (replay / conflict / in-progress), ETag `If-Match`, cache invalidation, audit, webhooks
- GraphQL parity: same auth, RBAC and row-level as REST

### Studio API + BFF
- `/studio/*` requires the Studio key or OIDC; Studio responses mask secrets
- BFF: signed session cookie, cross-site writes blocked, data proxy only for signed-in users

### UI (when `apps/web` changed)
- `npm run typecheck && npm run lint && npm test`
- e2e: `npm run test:e2e` against the Docker stack (wizard + editor specs)

## Tests

```bash
cd backend && pytest -q && ruff check .
cd apps/web && npm test && npm run typecheck && npm run lint
```

Cover at least: happy path, unauthenticated, forbidden (role/RBAC/row-level), invalid input,
not found, and each error type the change can raise.

## Failure Loop

1. Read the traceback / Problem Details body.
2. Fix the product bug (not the test, unless the expectation is wrong).
3. Re-run the scoped tests, then the full suite.

Avoid unrelated refactoring. Do not commit unless requested.

## Final Report

Verified flows and scenarios, sample data used, test results, bugs found and files changed, blockers.
