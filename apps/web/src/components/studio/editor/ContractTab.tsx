"use client";

import { pathError } from "@/lib/pathRules";
import { ALL_FILTER_OPS, ALL_METHODS } from "@/lib/types";
import styles from "../studio.module.css";
import { type EditorState } from "./useEditorState";

export function ContractTab({ s }: { s: EditorState }) {
  const { spec, selected, endpoint, updateEndpoint, toggleField, toggleMethod } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
    <div className={styles.editorBlock}>
      <div className={styles.metaGrid}>
        <label>
          Endpoint name
          <input
            value={endpoint.name}
            onChange={(e) => updateEndpoint({ name: e.target.value })}
            spellCheck={false}
          />
        </label>
        <label>
          Address (URL path)
          <input
            value={endpoint.path}
            onChange={(e) => updateEndpoint({ path: e.target.value })}
            spellCheck={false}
            aria-invalid={Boolean(pathError(endpoint.path, spec.app.api_prefix ?? ""))}
          />
          {pathError(endpoint.path, spec.app.api_prefix ?? "") && (
            <span className={styles.errLine} role="alert">
              {pathError(endpoint.path, spec.app.api_prefix ?? "")}
            </span>
          )}
        </label>
        <label>
          Unique id column
          <select
            value={endpoint.primary_key}
            onChange={(e) => updateEndpoint({ primary_key: e.target.value })}
          >
            {endpoint.fields.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <label>
          Paging style
          <select
            value={endpoint.pagination?.mode ?? "cursor"}
            onChange={(e) =>
              updateEndpoint({
                pagination: {
                  enabled: endpoint.pagination?.enabled ?? true,
                  mode: e.target.value as "cursor" | "offset",
                  default_limit: endpoint.pagination?.default_limit ?? 20,
                  max_limit: endpoint.pagination?.max_limit ?? 100,
                },
              })
            }
          >
            <option value="cursor">Next-page links (fast, recommended)</option>
            <option value="offset">Page numbers (offset)</option>
          </select>
        </label>
        <label>
          Rows per page (default)
          <input
            type="number"
            min={1}
            value={endpoint.pagination?.default_limit ?? 20}
            onChange={(e) =>
              updateEndpoint({
                pagination: {
                  enabled: endpoint.pagination?.enabled ?? true,
                  mode: endpoint.pagination?.mode ?? "cursor",
                  default_limit: Number(e.target.value) || 1,
                  max_limit: endpoint.pagination?.max_limit ?? 100,
                },
              })
            }
          />
        </label>
        <label>
          Rows per page (maximum)
          <input
            type="number"
            min={1}
            value={endpoint.pagination?.max_limit ?? 100}
            onChange={(e) =>
              updateEndpoint({
                pagination: {
                  enabled: endpoint.pagination?.enabled ?? true,
                  mode: endpoint.pagination?.mode ?? "cursor",
                  default_limit: endpoint.pagination?.default_limit ?? 20,
                  max_limit: Number(e.target.value) || 1,
                },
              })
            }
          />
        </label>
        <label className={styles.span2}>
          Description
          <input
            value={endpoint.description ?? ""}
            onChange={(e) => updateEndpoint({ description: e.target.value })}
          />
        </label>
      </div>
      <label className={styles.check}>
        <input
          type="checkbox"
          checked={endpoint.pagination?.enabled ?? true}
          onChange={(e) =>
            updateEndpoint({
              pagination: {
                enabled: e.target.checked,
                mode: endpoint.pagination?.mode ?? "cursor",
                default_limit: endpoint.pagination?.default_limit ?? 20,
                max_limit: endpoint.pagination?.max_limit ?? 100,
              },
            })
          }
        />
        Split results into pages
      </label>
      <label className={styles.check}>
        <input
          type="checkbox"
          checked={endpoint.allow_sensitive ?? false}
          onChange={(e) => updateEndpoint({ allow_sensitive: e.target.checked })}
        />
        Allow private-looking columns (passwords, tokens, keys)
      </label>

      {!endpoint.sql && (
        <>
          <h3>Allowed operations</h3>
          <div className={styles.allowlist}>
            {ALL_METHODS.map((m) => (
              <button
                key={m}
                type="button"
                className={[
                  styles.chip,
                  endpoint.methods.includes(m) ? styles.chipOn : "",
                ].join(" ")}
                onClick={() => toggleMethod(m)}
              >
                {m}
              </button>
            ))}
          </div>
        </>
      )}

      <h3>Fields in the response</h3>
      <div className={styles.allowlist}>
        {(selected?.columns ?? endpoint.fields.map((name) => ({ name, sensitive: false, primary_key: name === endpoint.primary_key, type: "", nullable: true }))).map(
          (col) => {
            const name = typeof col === "string" ? col : col.name;
            const on = endpoint.fields.includes(name);
            const sensitive = typeof col === "object" && col.sensitive;
            return (
              <button
                key={name}
                type="button"
                className={[
                  styles.chip,
                  on ? styles.chipOn : "",
                  sensitive ? styles.chipWarn : "",
                ].join(" ")}
                onClick={() => toggleField(name, "fields")}
              >
                {name}
              </button>
            );
          },
        )}
      </div>

      <div className={styles.twoCol}>
        <div>
          <h3>Can filter by</h3>
          <div className={styles.allowlist}>
            {endpoint.fields.map((f) => (
              <button
                key={f}
                type="button"
                className={[
                  styles.chip,
                  endpoint.filters.includes(f) ? styles.chipOn : "",
                ].join(" ")}
                onClick={() => toggleField(f, "filters")}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <div>
          <h3>Can sort by</h3>
          <div className={styles.allowlist}>
            {endpoint.fields.map((f) => (
              <button
                key={f}
                type="button"
                className={[
                  styles.chip,
                  endpoint.sortable.includes(f) ? styles.chipOn : "",
                ].join(" ")}
                onClick={() => toggleField(f, "sortable")}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!endpoint.sql && (
        <div>
          <h3>Fields callers may change</h3>
          <div className={styles.allowlist}>
            {endpoint.fields
              .filter((f) => f !== endpoint.primary_key)
              .map((f) => (
                <button
                  key={f}
                  type="button"
                  className={[
                    styles.chip,
                    (endpoint.writable_fields ?? []).includes(f) ? styles.chipOn : "",
                  ].join(" ")}
                  onClick={() => toggleField(f, "writable_fields")}
                >
                  {f}
                </button>
              ))}
          </div>
        </div>
      )}

      <details className={styles.advanced}>
        <summary>Advanced: filter types, bulk writes and file exports</summary>
      <h3>Filter types</h3>
      <div className={styles.allowlist}>
        {ALL_FILTER_OPS.map((op) => {
          const on = (endpoint.filter_operators ?? [...ALL_FILTER_OPS]).includes(op);
          return (
            <button
              key={op}
              type="button"
              className={[styles.chip, on ? styles.chipOn : ""].join(" ")}
              onClick={() => {
                const cur = new Set(endpoint.filter_operators ?? [...ALL_FILTER_OPS]);
                if (cur.has(op)) cur.delete(op);
                else cur.add(op);
                updateEndpoint({ filter_operators: [...cur] });
              }}
            >
              {op}
            </button>
          );
        })}
      </div>

      <div className={styles.rowGap}>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={endpoint.bulk_enabled ?? true}
            disabled={!!endpoint.sql}
            onChange={(e) => updateEndpoint({ bulk_enabled: e.target.checked })}
          />
          Bulk POST
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={endpoint.async_writes ?? false}
            disabled={!!endpoint.sql}
            onChange={(e) => updateEndpoint({ async_writes: e.target.checked })}
          />
          Async 202 writes
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={endpoint.csv_export ?? true}
            onChange={(e) => updateEndpoint({ csv_export: e.target.checked })}
          />
          CSV export
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={endpoint.ndjson_export ?? false}
            onChange={(e) => updateEndpoint({ ndjson_export: e.target.checked })}
          />
          NDJSON export
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={endpoint.parquet_export ?? false}
            onChange={(e) => updateEndpoint({ parquet_export: e.target.checked })}
          />
          Parquet export (requires pyarrow)
        </label>
      </div>
      </details>
    </div>
    </>
  );
}
