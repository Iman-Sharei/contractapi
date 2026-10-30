# Upgrading

## 0.4.x → 0.5.0b1

1. **PyPI name:** install `contractapi` (not `contractapi`). Import is `import contractapi`.
2. **Studio env:** move secrets to server-only `STUDIO_API_KEY` / `DATA_API_KEY` (see `apps/web/.env.example`).
3. **Activate persistence:** active APIs are restored from `SPECS_DIR/.runtime/active.json` on boot.
4. **Webhooks:** failed deliveries retry with backoff; exhausted events land in `SPECS_DIR/.runtime/webhook-dlq.jsonl`.
5. **Experimental flags:** set `DATAAPI_EXPERIMENTAL=graphql,duckdb,parquet,oidc,queue` (comma list) or `all` to enable opt-in surfaces that were previously always-on when deps exist.

### YAML

No required field renames in 0.5b1. New optional fields: `parquet_export`, `database.driver`.
