"use client";

import { WEBHOOK_EVENTS } from "@/lib/types";
import styles from "../studio.module.css";
import { type EditorState } from "./useEditorState";

export function WebhooksSection({ s }: { s: EditorState }) {
  const { spec, patchWebhook, addWebhook, removeWebhook } = s;
  return (
    <>
      <h3>Webhooks</h3>
      <p className={styles.hint}>
        POST JSON on writes. Signature header <code>X-Contractapi-Signature</code> when
        secret is set.
      </p>
      {(spec.app.webhooks ?? []).map((wh, idx) => (
        <div key={idx} className={styles.relCard}>
          <label>
            URL
            <input
              value={wh.url}
              onChange={(e) => patchWebhook(idx, { url: e.target.value })}
              placeholder="https://hooks.example.com/contractapi"
            />
          </label>
          <div className={styles.toggleRow}>
            {WEBHOOK_EVENTS.map((ev) => (
              <label key={ev} className={styles.check}>
                <input
                  type="checkbox"
                  checked={(wh.events ?? []).includes(ev)}
                  onChange={(e) => {
                    const set = new Set(wh.events ?? []);
                    if (e.target.checked) set.add(ev);
                    else set.delete(ev);
                    patchWebhook(idx, { events: [...set] });
                  }}
                />
                {ev}
              </label>
            ))}
          </div>
          <div className={styles.twoCol}>
            <label>
              HMAC secret
              <input
                value={wh.secret ?? ""}
                onChange={(e) => patchWebhook(idx, { secret: e.target.value })}
              />
            </label>
            <label>
              Timeout (s)
              <input
                type="number"
                min={0.5}
                max={30}
                step={0.5}
                value={wh.timeout_seconds ?? 3}
                onChange={(e) =>
                  patchWebhook(idx, {
                    timeout_seconds: Number(e.target.value) || 3,
                  })
                }
              />
            </label>
          </div>
          <button
            type="button"
            className={styles.dangerBtn}
            onClick={() => removeWebhook(idx)}
          >
            Remove webhook
          </button>
        </div>
      ))}
      <button type="button" className={styles.secondary} onClick={addWebhook}>
        + Add webhook
      </button>

    </>
  );
}
