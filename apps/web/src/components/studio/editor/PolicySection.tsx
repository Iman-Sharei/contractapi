"use client";

import styles from "../studio.module.css";
import { type EditorState } from "./useEditorState";

export function PolicySection({ s }: { s: EditorState }) {
  const { spec, endpoint, patchApp, updateEndpoint } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
      <div className={styles.twoCol}>
        <label>
          Deprecation sunset (YYYY-MM-DD)
          <input
            value={endpoint.deprecation?.sunset ?? ""}
            onChange={(e) =>
              updateEndpoint({
                deprecation: {
                  deprecated: Boolean(e.target.value),
                  sunset: e.target.value || null,
                  successor: endpoint.deprecation?.successor ?? null,
                },
              })
            }
          />
        </label>
        <label>
          Successor path
          <input
            value={endpoint.deprecation?.successor ?? ""}
            onChange={(e) =>
              updateEndpoint({
                deprecation: {
                  deprecated: true,
                  sunset: endpoint.deprecation?.sunset ?? null,
                  successor: e.target.value || null,
                },
              })
            }
          />
        </label>
      </div>
      <label>
        IP allowlist (comma-separated IPs / prefixes)
        <input
          value={(spec.app.ip_allowlist ?? []).join(", ")}
          onChange={(e) =>
            patchApp({
              ip_allowlist: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          placeholder="127.0.0.1, 10.0.0."
        />
      </label>

    </>
  );
}
