# Upgrading

## 0.4.x → 0.5.0

1. **PyPI name:** install `contractapi`. Import is `import contractapi`.
2. **Studio env:** move secrets to server-only `STUDIO_API_KEY` / `DATA_API_KEY` (see `apps/web/.env.example`).
3. **Activate persistence:** active APIs are restored from `SPECS_DIR/.runtime/active.json` on boot.
4. **Webhooks:** failed deliveries retry with backoff; exhausted events land in `SPECS_DIR/.runtime/webhook-dlq.jsonl`.
5. **Experimental flags:** set `CONTRACTAPI_EXPERIMENTAL` / `DATAAPI_EXPERIMENTAL` (comma list or `all`) for GraphQL, OIDC, queue, multi_active. **Parquet** and **DuckDB** are GA — install extras only; `parquet` / `duckdb` experimental tokens are ignored.
6. **API prefix:** Studio wizard default is empty (no `/v1`). Existing specs keep their stored prefix.

### YAML

No required field renames in 0.5.0. New optional fields: `parquet_export`, `database.driver`, `app.jwt` tunables already present.
