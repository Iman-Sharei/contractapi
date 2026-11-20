"use client";

import { getDataApiKey } from "@/lib/api";
import styles from "./editor.module.css";
import { type EditorState } from "./useEditorState";

export function RbacSection({ s }: { s: EditorState }) {
  const { spec, addRbacRole, updateRbacRole, removeRbacRole, toggleRbacField } = s;
  return (
    <>
      <h3>RBAC field matrix</h3>
      <p className={styles.hint}>
        Per-role allowlists of response fields. Empty matrix = no extra filtering. Data
        key for try-it: <code>{getDataApiKey()}</code>
      </p>
      {(spec.app.rbac ?? []).map((role, idx) => (
        <div key={idx} className={styles.relCard}>
          <div className={styles.settingsHead}>
            <label>
              Role
              <input
                value={role.role}
                onChange={(e) => updateRbacRole(idx, { role: e.target.value })}
              />
            </label>
            <button
              type="button"
              className={styles.dangerBtn}
              onClick={() => removeRbacRole(idx)}
            >
              Remove
            </button>
          </div>
          {spec.endpoints.map((ep) => (
            <div key={ep.name}>
              <strong>{ep.name}</strong>
              <div className={styles.toggleRow}>
                {ep.fields.map((f) => (
                  <label key={f} className={styles.check}>
                    <input
                      type="checkbox"
                      checked={(role.endpoints[ep.name] ?? []).includes(f)}
                      onChange={() => toggleRbacField(idx, ep.name, f)}
                    />
                    {f}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
      <button type="button" className={styles.secondary} onClick={addRbacRole}>
        + Add RBAC role
      </button>
    </>
  );
}
