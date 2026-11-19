"use client";

import styles from "../studio.module.css";
import { type EditorState } from "./useEditorState";

export function ApiSurfaceCard({ s }: { s: EditorState }) {
  const { spec, patchApp } = s;
  return (
    <section className={styles.settingsCard}>
      <div className={styles.settingsHead}>
        <h2>About this API</h2>
      </div>
      <div className={styles.fieldGrid}>
        <label className={styles.span2}>
          <span className={styles.fieldLabel}>Title</span>
          <input value={spec.app.title} onChange={(e) => patchApp({ title: e.target.value })} />
        </label>
        <label>
          <span className={styles.fieldLabel}>Version</span>
          <input value={spec.app.version} onChange={(e) => patchApp({ version: e.target.value })} />
        </label>
        <label className={styles.span3}>
          <span className={styles.fieldLabel}>Description</span>
          <input
            value={spec.app.description}
            onChange={(e) => patchApp({ description: e.target.value })}
          />
        </label>
      </div>

      <details className={styles.advanced}>
        <summary>Advanced: speed, limits and safety switches</summary>
      <div className={styles.toggleRow}>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={spec.app.read_only}
            onChange={(e) => patchApp({ read_only: e.target.checked })}
          />
          <span>Read-only</span>
        </label>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={spec.app.cache?.enabled ?? true}
            onChange={(e) =>
              patchApp({
                cache: {
                  enabled: e.target.checked,
                  ttl_seconds: spec.app.cache?.ttl_seconds ?? 30,
                },
              })
            }
          />
          <span>Cache</span>
        </label>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={spec.app.rate_limit.enabled}
            onChange={(e) =>
              patchApp({
                rate_limit: {
                  ...spec.app.rate_limit,
                  enabled: e.target.checked,
                },
              })
            }
          />
          <span>Rate limit</span>
        </label>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={spec.app.idempotency?.enabled ?? true}
            onChange={(e) =>
              patchApp({
                idempotency: {
                  enabled: e.target.checked,
                  required_for_writes: spec.app.idempotency?.required_for_writes ?? false,
                  ttl_seconds: spec.app.idempotency?.ttl_seconds ?? 86400,
                },
              })
            }
          />
          <span>Idempotency</span>
        </label>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={spec.app.idempotency?.required_for_writes ?? false}
            onChange={(e) =>
              patchApp({
                idempotency: {
                  enabled: spec.app.idempotency?.enabled ?? true,
                  required_for_writes: e.target.checked,
                  ttl_seconds: spec.app.idempotency?.ttl_seconds ?? 86400,
                },
              })
            }
          />
          <span>Idempotency required</span>
        </label>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={spec.app.compression ?? true}
            onChange={(e) => patchApp({ compression: e.target.checked })}
          />
          <span>Gzip</span>
        </label>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={spec.app.audit_enabled ?? true}
            onChange={(e) => patchApp({ audit_enabled: e.target.checked })}
          />
          <span>Audit</span>
        </label>
      </div>

      <div className={styles.fieldGrid}>
        <label>
          <span className={styles.fieldLabel}>Cache TTL (s)</span>
          <input
            type="number"
            min={0}
            value={spec.app.cache?.ttl_seconds ?? 30}
            onChange={(e) =>
              patchApp({
                cache: {
                  enabled: spec.app.cache?.enabled ?? true,
                  ttl_seconds: Number(e.target.value) || 0,
                },
              })
            }
          />
        </label>
        <label>
          <span className={styles.fieldLabel}>Rate / min</span>
          <input
            type="number"
            min={1}
            value={spec.app.rate_limit.requests_per_minute}
            onChange={(e) =>
              patchApp({
                rate_limit: {
                  ...spec.app.rate_limit,
                  requests_per_minute: Number(e.target.value) || 1,
                },
              })
            }
          />
        </label>
        <label>
          <span className={styles.fieldLabel}>Idempotency TTL (s)</span>
          <input
            type="number"
            min={0}
            value={spec.app.idempotency?.ttl_seconds ?? 86400}
            onChange={(e) =>
              patchApp({
                idempotency: {
                  enabled: spec.app.idempotency?.enabled ?? true,
                  required_for_writes: spec.app.idempotency?.required_for_writes ?? false,
                  ttl_seconds: Number(e.target.value) || 0,
                },
              })
            }
          />
        </label>
      </div>
      </details>
    </section>
  );
}
