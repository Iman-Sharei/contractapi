"use client";

import { Button, Card, CardBody, CardHeader, Method } from "@/components/ui/primitives";
import { AUTH_OPTIONS } from "@/lib/labels";
import { formatApiPath } from "@/lib/pickColumns";
import { SafetyChecklist } from "../SafetyChecklist";
import { UseYourApi } from "../UseYourApi";
import type { EditorState } from "../editor/useEditorState";
import styles from "../pages.module.css";

export function OverviewTab({
  s,
  name,
  refreshKey,
  onEdit,
}: {
  s: EditorState;
  name: string;
  refreshKey: number;
  onEdit: () => void;
}) {
  const { spec } = s;
  const access = AUTH_OPTIONS.find((o) => o.value === spec.app.auth);
  return (
    <div className={styles.overviewGrid}>
      <UseYourApi name={name} refreshKey={refreshKey} />

      <div className={styles.overviewSide}>
        <Card>
          <CardHeader
            icon="layers"
            title="At a glance"
            actions={
              <Button size="sm" variant="ghost" icon="settings" onClick={onEdit}>
                Edit
              </Button>
            }
          />
          <CardBody>
            <dl className={styles.facts}>
              <div>
                <dt>Access</dt>
                <dd>{access?.label.replace(" (recommended)", "") ?? spec.app.auth}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{spec.app.version}</dd>
              </div>
              <div>
                <dt>Changes allowed</dt>
                <dd>{spec.app.read_only ? "Read-only" : "Create / update / delete"}</dd>
              </div>
            </dl>
            <ul className={styles.endpointList} aria-label="Endpoints">
              {spec.endpoints.map((ep) => (
                <li key={ep.name}>
                  <span className={styles.methods}>
                    {(ep.sql ? ["GET"] : ep.methods).map((m) => (
                      <Method key={m} method={m} />
                    ))}
                  </span>
                  <code>{formatApiPath(spec.app.api_prefix ?? "", ep.path)}</code>
                  <span className={styles.endpointMeta}>{ep.fields.length} fields</span>
                </li>
              ))}
              {spec.endpoints.length === 0 && <li className={styles.muted}>No endpoints yet.</li>}
            </ul>
          </CardBody>
        </Card>
        <Card pad>
          <SafetyChecklist spec={spec} title="Before you share it" />
        </Card>
      </div>
    </div>
  );
}
