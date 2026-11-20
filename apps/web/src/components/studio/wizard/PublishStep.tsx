"use client";

import { SafetyChecklist } from "@/components/studio/SafetyChecklist";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Banner, Button, Card, CardBody, CardHeader, Hint, Method, Switch, cx, ui } from "@/components/ui/primitives";
import { getApiBase } from "@/lib/api";
import { AUTH_OPTIONS } from "@/lib/labels";
import { formatApiPath } from "@/lib/pickColumns";
import type { ApiSpecDraft } from "@/lib/types";
import styles from "../pages.module.css";

type Auth = ApiSpecDraft["app"]["auth"];

const AUTH_ICON: Record<Auth, IconName> = { api_key: "key", jwt: "user", none: "globe" };

type Props = {
  draft: ApiSpecDraft;
  title: string;
  setTitle: (v: string) => void;
  prefix: string;
  setPrefix: (v: string) => void;
  auth: Auth;
  setAuth: (v: Auth) => void;
  allowWrites: boolean;
  setAllowWrites: (v: boolean) => void;
  apiName: string;
  nameTaken: boolean;
  pending: boolean;
  onBack: () => void;
  onPublish: (live: boolean) => void;
};

/** Step 3 — access, optional editing, a plain review, then publish. */
export function PublishStep(p: Props) {
  const base = `${getApiBase()}/apis/${p.apiName}`;
  return (
    <div className={styles.publishGrid}>
      <Card data-testid="wizard-guards">
        <CardHeader icon="shield" title="Protect & publish" description="Decide who may call the API and what they may do." />
        <CardBody className={ui.stack}>
          <div className={ui.formGrid}>
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
              <Hint>
                <code>v1</code> gives addresses like <code>/v1/customers</code>, so a future v2 can live
                next to it.
              </Hint>
            </label>
          </div>

          <fieldset className={styles.choiceSet}>
            <legend>Who can use it?</legend>
            {AUTH_OPTIONS.map((o) => (
              <label key={o.value} className={cx(styles.choice, p.auth === o.value && styles.choiceOn)}>
                <input
                  type="radio"
                  name="auth"
                  value={o.value}
                  checked={p.auth === o.value}
                  onChange={() => p.setAuth(o.value)}
                />
                <span className={styles.choiceIcon}>
                  <Icon name={AUTH_ICON[o.value]} size={17} />
                </span>
                <span className={styles.choiceText}>
                  <strong>{o.label}</strong>
                  <span>{o.help}</span>
                </span>
              </label>
            ))}
          </fieldset>
          {p.auth === "none" && (
            <Banner tone="warning" role="note">
              Anyone who knows the address can read this data. Use it only for data that is already
              public.
            </Banner>
          )}

          <Switch
            label="Also allow adding, changing and deleting rows"
            description="Off = read-only (safest). You can fine-tune which fields may change later."
            checked={p.allowWrites}
            onChange={(e) => p.setAllowWrites(e.target.checked)}
            data-testid="wizard-allow-writes"
          />
          {p.allowWrites && (
            <Banner tone="warning" role="note">
              Callers will be able to change data in your database. Keep a key on it, and consider
              limiting which fields can be changed in the editor afterwards.
            </Banner>
          )}
        </CardBody>
      </Card>

      <Card className={styles.review}>
        <CardHeader icon="checkCircle" title="Review" description="This is what goes live." />
        <CardBody className={ui.stack}>
          <div>
            <span className={styles.reviewLabel}>Address</span>
            <code className={styles.reviewAddress}>{base}</code>
          </div>
          <div>
            <span className={styles.reviewLabel}>Your API will have</span>
            <ul className={styles.endpointList} aria-label="Endpoints">
              {p.draft.endpoints.map((ep) => (
                <li key={ep.name}>
                  <span className={styles.methods}>
                    {ep.methods.map((m) => (
                      <Method key={m} method={m} />
                    ))}
                  </span>
                  <code>{formatApiPath(p.draft.app.api_prefix ?? "", ep.path)}</code>
                  <span className={styles.endpointMeta}>{ep.fields.length} fields</span>
                </li>
              ))}
            </ul>
          </div>
          <SafetyChecklist spec={p.draft} />
          {p.nameTaken && (
            <Banner tone="warning" role="alert">
              Publishing will replace the existing API <code>{p.apiName}</code>.
            </Banner>
          )}
        </CardBody>
      </Card>

      <div className={styles.publishBar}>
        <Button variant="ghost" icon="arrowLeft" onClick={p.onBack}>
          Back
        </Button>
        <span className={styles.pushRight} />
        <Button variant="secondary" onClick={() => p.onPublish(false)} disabled={p.pending}>
          Save as draft
        </Button>
        <Button
          variant="primary"
          size="lg"
          icon="zap"
          data-testid="wizard-save-activate"
          onClick={() => p.onPublish(true)}
          busy={p.pending}
          disabled={p.pending}
        >
          {p.pending ? "Publishing…" : "Publish API"}
        </Button>
      </div>
    </div>
  );
}
