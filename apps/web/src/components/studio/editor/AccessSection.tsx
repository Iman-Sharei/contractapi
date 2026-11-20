"use client";

import styles from "./editor.module.css";
import { type EditorState } from "./useEditorState";

export function AccessSection({ s }: { s: EditorState }) {
  const { endpoint, updateEndpoint } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
      <h3>Endpoint access</h3>
      <label>
        Required roles (comma-separated)
        <input
          value={(endpoint.roles ?? []).join(", ")}
          onChange={(e) =>
            updateEndpoint({
              roles: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          placeholder="analyst, admin"
        />
      </label>
      <label>
        ETag field
        <select
          value={endpoint.etag_field ?? ""}
          onChange={(e) =>
            updateEndpoint({ etag_field: e.target.value || null })
          }
        >
          <option value="">(hash body)</option>
          {endpoint.fields.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <div className={styles.twoCol}>
        <label>
          Soft-delete column
          <input
            value={endpoint.soft_delete?.column ?? ""}
            disabled={!!endpoint.sql}
            onChange={(e) =>
              updateEndpoint({
                soft_delete: e.target.value
                  ? { column: e.target.value }
                  : null,
              })
            }
            placeholder="deleted_at"
          />
        </label>
        <label>
          Row-level column
          <input
            value={endpoint.row_level?.column ?? ""}
            disabled={!!endpoint.sql}
            onChange={(e) =>
              updateEndpoint({
                row_level: e.target.value
                  ? {
                      column: e.target.value,
                      claim: endpoint.row_level?.claim ?? "sub",
                      required: endpoint.row_level?.required ?? true,
                    }
                  : null,
              })
            }
            placeholder="owner_id"
          />
        </label>
      </div>
      {endpoint.row_level && (
        <div className={styles.twoCol}>
          <label>
            JWT claim for row-level
            <input
              value={endpoint.row_level.claim}
              onChange={(e) =>
                updateEndpoint({
                  row_level: { ...endpoint.row_level!, claim: e.target.value },
                })
              }
            />
          </label>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={endpoint.row_level.required}
              onChange={(e) =>
                updateEndpoint({
                  row_level: {
                    ...endpoint.row_level!,
                    required: e.target.checked,
                  },
                })
              }
            />
            Require claim
          </label>
        </div>
      )}

    </>
  );
}
