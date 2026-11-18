# Errors: RFC 9457 Problem Details

All client-visible failures are `application/problem+json` produced by `core/errors.py`.

## Use

```python
from contractapi.core.errors import AppError

raise AppError(
    type_="https://contractapi.dev/problems/not-found",
    title="Not Found",
    status=404,
    detail="Endpoint 'customers' is not part of the active API.",
    extensions={"endpoint": "customers"},   # optional, small, non-secret
)
```

- Handlers already registered: `AppError`, Starlette `HTTPException`, `RequestValidationError` (→ 422 `validation-error`). Don't add parallel error formats.
- `type_` is `https://contractapi.dev/problems/<kebab-slug>`. **Reuse an existing slug** when it fits (`not-found`, `forbidden`, `unauthorized`, `invalid-filter`, `invalid-cursor`, `invalid-sort`, `invalid-fields`, `invalid-include`, `invalid-token`, `rate-limited`, `idempotency-conflict`, `precondition-failed`, `payload-too-large`, `dependency-missing`, `misconfigured`, `database-error`, `database-unreachable`, …). Grep `problems/` before inventing one; a new failure mode gets a new stable slug.
- `title` is stable per type; `detail` is the instance-specific, **actionable** message (for non-expert Studio users: say what to change).
- Pick the right status: 400 bad input/business rule, 401 unauthenticated, 403 forbidden, 404 missing, 409 conflict, 412 precondition, 413 too large, 422 validation, 429 rate limit.

## Avoid

- Raising `ValueError`/`KeyError`/`RuntimeError`/bare `Exception` from code reachable by a request — they become opaque 500s. (Domain-model validators in `spec.py` may raise `ValueError`/Pydantic errors; the Studio validate route converts them to `invalid-spec`.)
- `HTTPException` with a plain string for new code — use `AppError`.
- Leaking internals: no SQL text, stack traces, connection strings, file paths or driver messages in `detail`/`extensions`. Map low-level errors at the use-case edge:

```python
try:
    rows = conn.execute(stmt, params).mappings().all()
except OperationalError:
    raise AppError(type_=".../database-unreachable", title="Database unreachable", status=400,
                   detail="Could not reach the database. Check host, port and network access.")
except DBAPIError:
    raise AppError(type_=".../database-error", title="Database error", status=400,
                   detail="The database rejected the query.")
```

- Repeating the same type URI literal many times in new code: put it in a module-level constant.
