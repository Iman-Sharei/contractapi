"use client";

import { SafetyChecklist } from "@/components/studio/SafetyChecklist";
import { AUTH_OPTIONS, authHelp } from "@/lib/labels";
import { formatApiPath } from "@/lib/pickColumns";
import type { ApiSpecDraft } from "@/lib/types";
import styles from "../flow.module.css";

type Props = {
  draft: ApiSpecDraft;
  title: string;
  setTitle: (v: string) => void;
  prefix: string;
  setPrefix: (v: string) => void;
  auth: ApiSpecDraft["app"]["auth"];
  setAuth: (v: ApiSpecDraft["app"]["auth"]) => void;
  allowWrites: boolean;
  setAllowWrites: (v: boolean) => void;
  apiName: string;
  nameTaken: boolean;
  pending: boolean;
  onBack: () => void;
  onPublish: (live: boolean) => void;
};

/** Step 3 — access, optional editing, a plain summary, then publish. */
export function PublishStep(p: Props) {
  return (
    <section className={styles.panel} data-testid="wizard-guards">
      <h2>Protect &amp; publish</h2>
      <div className={styles.formGrid}>
        <label>
          Title (shown in the docs)
          <input value={p.title} onChange={(e) => p.setTitle(e.target.value)} />
        </label>
        <label>
          Version in the address (optional)
          <input
            value={p.prefix}
            onChange={(e) => p.setPrefix(e.target.value)}
            placeholder="e.g. v1"
            spellCheck={false}
          />
          <span className={styles.hint}>
            Adding <code>v1</code> makes addresses like <code>/v1/customers</code>, so a future v2 can
            live next to it.
          </span>
        </label>
        <label className={styles.span2}>
          Who can use it?
          <select value={p.auth} onChange={(e) => p.setAuth(e.target.value as Props["auth"])}>
            {AUTH_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <span className={styles.hint}>{authHelp(p.auth)}</span>
        </label>
        <label className={`${styles.checkField} ${styles.span2}`}>
          <input
            type="checkbox"
            checked={p.allowWrites}
            onChange={(e) => p.setAllowWrites(e.target.checked)}
            data-testid="wizard-allow-writes"
          />
          Also allow adding, changing and deleting rows
        </label>
      </div>
      {p.allowWrites && (
        <p className={styles.warnBox} role="note">
          Callers will be able to change data in your database. Keep a key on it, and consider
          limiting which fields can be changed in the editor afterwards.
        </p>
      )}

      <h3>Your API will have</h3>
      <ul className={styles.chipRow} aria-label="Endpoints">
        {p.draft.endpoints.map((ep) => (
          <li key={ep.name} className={styles.chipOn}>
            {ep.methods.join(" · ")} {formatApiPath(p.draft.app.api_prefix ?? "", ep.path)}
            <span className={styles.chipMeta}> · {ep.fields.length} fields</span>
          </li>
        ))}
      </ul>
      <SafetyChecklist spec={p.draft} />
      {p.nameTaken && (
        <p className={styles.warnBox} role="alert">
          Publishing will replace the existing API <code>{p.apiName}</code>.
        </p>
      )}
      <div className={styles.toolbar}>
        <button type="button" className={styles.ghost} onClick={p.onBack}>
          Back
        </button>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => p.onPublish(false)}
          disabled={p.pending}
        >
          Save as draft
        </button>
        <button
          type="button"
          className={styles.primary}
          data-testid="wizard-save-activate"
          onClick={() => p.onPublish(true)}
          disabled={p.pending}
        >
          {p.pending ? "Publishing…" : "Publish API"}
        </button>
      </div>
    </section>
  );
}
