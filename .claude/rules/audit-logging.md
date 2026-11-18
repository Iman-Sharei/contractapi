# Audit logging

Every data-plane **write** and every security-relevant outcome emits an audit event. Implementation: `infrastructure/audit.py::audit_event` (append-only JSONL at `settings.audit_log_path` + in-memory ring for `recent_events`), surfaced in Studio Ops.

## Where

- Data plane: through the `_audit(spec, action, endpoint, request, ...)` helper in `application/data_api_builder.py`. It honors `spec.app.audit_enabled` and attaches the principal (`sub`, `roles`). Call it **after** the outcome succeeds.
- Control plane (activate, save/delete spec, API-key create/revoke, token issue, promote): call `audit_event` from the `application/` function that owns the outcome.
- **Not** in routers' parsing code, Pydantic schemas, or domain models.

## How

```python
_audit(spec, "update", endpoint, request, status=200, resource_id=item_id)
audit_event(action="studio.spec.activate", endpoint=None, principal=None, status=200, meta={"name": spec_name})
```

- `action` is a stable dotted/lowercase verb (`create`, `update`, `delete`, `create.async`, `studio.spec.activate`). Reuse existing values; don't invent synonyms. New feature → new action string in the same change as the use case.
- `meta`: small IDs, counts, changed **field names**, job ids. **Never** request bodies, passwords, API keys, JWTs, refresh tokens, OTP/secrets, or full row data.

## When

| Outcome | Log |
|---|---|
| create / update / delete / bulk / async job accepted | always |
| spec activate/deactivate/delete, key issue/revoke, token issue/refresh/revoke | always |
| auth failure, forbidden, rate-limit on privileged paths | log if peers do; otherwise metrics only |
| plain reads | skip unless the endpoint exposes scoped/sensitive data already patterned |
| validation reject before any side effect | skip |
