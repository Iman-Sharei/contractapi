"use client";

import { Card, CardBody, CardHeader, Switch, ui } from "@/components/ui/primitives";
import { type EditorState } from "./useEditorState";
import styles from "./editor.module.css";

export function ApiSurfaceCard({ s }: { s: EditorState }) {
  const { spec, patchApp } = s;
  const cache = { enabled: spec.app.cache?.enabled ?? true, ttl_seconds: spec.app.cache?.ttl_seconds ?? 30 };
  const idem = {
    enabled: spec.app.idempotency?.enabled ?? true,
    required_for_writes: spec.app.idempotency?.required_for_writes ?? false,
    ttl_seconds: spec.app.idempotency?.ttl_seconds ?? 86400,
  };
  return (
    <Card>
      <CardHeader icon="book" title="About this API" description="Shown at the top of the interactive docs." />
      <CardBody className={ui.stack}>
        <div className={styles.fieldGrid}>
          <label className={styles.span2}>
            Title
            <input value={spec.app.title} onChange={(e) => patchApp({ title: e.target.value })} />
          </label>
          <label>
            Version
            <input value={spec.app.version} onChange={(e) => patchApp({ version: e.target.value })} />
          </label>
          <label className={styles.span3}>
            Description
            <input value={spec.app.description} onChange={(e) => patchApp({ description: e.target.value })} />
          </label>
        </div>

        <details className={styles.advanced}>
          <summary>Advanced: speed, limits and safety switches</summary>
          <div className={styles.switchGrid}>
            <Switch
              label="Read-only"
              description="Blocks every create, update and delete."
              checked={spec.app.read_only}
              onChange={(e) => patchApp({ read_only: e.target.checked })}
            />
            <Switch
              label="Cache answers"
              description="Repeat reads are served from memory for a few seconds."
              checked={cache.enabled}
              onChange={(e) => patchApp({ cache: { ...cache, enabled: e.target.checked } })}
            />
            <Switch
              label="Rate limit"
              description="Caps requests per minute for each caller."
              checked={spec.app.rate_limit.enabled}
              onChange={(e) => patchApp({ rate_limit: { ...spec.app.rate_limit, enabled: e.target.checked } })}
            />
            <Switch
              label="Safe retries (Idempotency-Key)"
              description="A repeated create with the same key is not stored twice."
              checked={idem.enabled}
              onChange={(e) => patchApp({ idempotency: { ...idem, enabled: e.target.checked } })}
            />
            <Switch
              label="Require Idempotency-Key on writes"
              description="Writes without the header are rejected."
              checked={idem.required_for_writes}
              onChange={(e) => patchApp({ idempotency: { ...idem, required_for_writes: e.target.checked } })}
            />
            <Switch
              label="Compress responses (gzip)"
              checked={spec.app.compression ?? true}
              onChange={(e) => patchApp({ compression: e.target.checked })}
            />
            <Switch
              label="Audit log"
              description="Records every change and who made it."
              checked={spec.app.audit_enabled ?? true}
              onChange={(e) => patchApp({ audit_enabled: e.target.checked })}
            />
          </div>

          <div className={styles.fieldGrid}>
            <label>
              Cache time (seconds)
              <input
                type="number"
                min={0}
                value={cache.ttl_seconds}
                onChange={(e) => patchApp({ cache: { ...cache, ttl_seconds: Number(e.target.value) || 0 } })}
              />
            </label>
            <label>
              Requests per minute
              <input
                type="number"
                min={1}
                value={spec.app.rate_limit.requests_per_minute}
                onChange={(e) =>
                  patchApp({
                    rate_limit: { ...spec.app.rate_limit, requests_per_minute: Number(e.target.value) || 1 },
                  })
                }
              />
            </label>
            <label>
              Retry window (seconds)
              <input
                type="number"
                min={0}
                value={idem.ttl_seconds}
                onChange={(e) => patchApp({ idempotency: { ...idem, ttl_seconds: Number(e.target.value) || 0 } })}
              />
            </label>
          </div>
        </details>
      </CardBody>
    </Card>
  );
}
