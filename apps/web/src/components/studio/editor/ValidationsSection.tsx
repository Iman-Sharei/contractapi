"use client";

import { VALIDATION_FORMATS } from "@/lib/types";
import styles from "../studio.module.css";
import { type EditorState } from "./useEditorState";

export function ValidationsSection({ s }: { s: EditorState }) {
  const { endpoint, addValidation, updateValidation, removeValidation } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
      <h3>Field validations</h3>
      <p className={styles.hint}>
        Extra checks on write payloads (format, length, range). Applied in addition to DB
        constraints.
      </p>
      {(endpoint.validations ?? []).map((v, idx) => (
        <div key={idx} className={styles.relCard}>
          <div className={styles.twoCol}>
            <label>
              Field
              <select
                value={v.field}
                onChange={(e) => updateValidation(idx, { field: e.target.value })}
              >
                {endpoint.fields.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Format
              <select
                value={v.format ?? ""}
                onChange={(e) =>
                  updateValidation(idx, { format: e.target.value || null })
                }
              >
                <option value="">(none)</option>
                {VALIDATION_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className={styles.twoCol}>
            <label>
              Min length
              <input
                type="number"
                value={v.min_length ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    min_length: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Max length
              <input
                type="number"
                value={v.max_length ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    max_length: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <div className={styles.twoCol}>
            <label>
              ≥ (ge)
              <input
                type="number"
                value={v.ge ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    ge: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              ≤ (le)
              <input
                type="number"
                value={v.le ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    le: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <label>
            Pattern (regex)
            <input
              value={v.pattern ?? ""}
              onChange={(e) =>
                updateValidation(idx, { pattern: e.target.value || null })
              }
              placeholder="^[A-Z].*"
            />
          </label>
          <button
            type="button"
            className={styles.dangerBtn}
            onClick={() => removeValidation(idx)}
          >
            Remove rule
          </button>
        </div>
      ))}
      <button type="button" className={styles.secondary} onClick={addValidation}>
        + Add validation
      </button>
    </>
  );
}
