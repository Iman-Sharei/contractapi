"use client";

import { useState } from "react";
import { Badge, Banner, Button, Card, CardBody, CardHeader, Hint } from "@/components/ui/primitives";
import { checkDatabaseChanges } from "@/lib/api";
import type { DatabaseChanges } from "@/lib/types";
import styles from "../pages.module.css";

const STATUS: Record<string, { label: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  ok: { label: "Matches", tone: "success" },
  changed: { label: "Changed", tone: "warning" },
  missing_table: { label: "Table gone", tone: "danger" },
  skipped: { label: "Custom SQL", tone: "neutral" },
};

/** Compare the saved API with its database now, so renamed or removed columns are found
 *  before callers hit them. */
export function DatabaseChangesCard({ name }: { name: string }) {
  const [report, setReport] = useState<DatabaseChanges | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setReport(await checkDatabaseChanges(name));
    } catch (e) {
      setReport(null);
      setError(e instanceof Error ? e.message : "Could not check the database.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        icon="database"
        title="Database changes"
        description="Did someone rename or remove a column this API uses?"
        actions={
          <Button size="sm" variant="secondary" icon="refresh" onClick={run} busy={busy} data-testid="check-db-changes">
            Check database changes
          </Button>
        }
      />
      <CardBody>
        {error && <Banner tone="danger">{error}</Banner>}
        {!report && !error && <Hint>Checks the saved version against the database right now. Nothing is changed.</Hint>}
        {report && (
          <div data-testid="db-changes-report">
            <Banner tone={report.ok ? "success" : "warning"}>
              {report.ok
                ? "The database still has every table and column this API uses."
                : "Some fields no longer exist. Callers get a “Database changed” error on those endpoints until you update them."}
            </Banner>
            <ul className={styles.endpointList}>
              {report.endpoints.map((ep) => (
                <li key={ep.name}>
                  <Badge tone={STATUS[ep.status]?.tone ?? "neutral"}>{STATUS[ep.status]?.label ?? ep.status}</Badge>
                  <code>{ep.name}</code>
                  <span className={styles.endpointMeta}>
                    {ep.missing.length > 0 && <>Missing: {ep.missing.join(", ")}. </>}
                    {ep.new_columns.length > 0 && <>New, not shared yet: {ep.new_columns.join(", ")}. </>}
                    {ep.detail}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
