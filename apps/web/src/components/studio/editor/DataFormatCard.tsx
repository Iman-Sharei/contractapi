"use client";

import { Card, CardBody, CardHeader, Hint, ui } from "@/components/ui/primitives";
import { type EditorState } from "./useEditorState";
import styles from "./editor.module.css";

const COMMON_ZONES = ["UTC", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Asia/Tehran", "Asia/Dubai", "Asia/Tokyo"];

/** How values look in responses: exact decimals, date-times with their time zone. */
export function DataFormatCard({ s }: { s: EditorState }) {
  const { spec, setSpec, patchApp } = s;
  const tz = spec.database.timezone ?? "";
  return (
    <Card>
      <CardHeader icon="code" title="Data format" description="How numbers and dates look in the answers." />
      <CardBody className={ui.stack}>
        <div className={styles.fieldGrid}>
          <label>
            Decimal numbers (money, prices)
            <select
              value={spec.app.decimals ?? "number"}
              data-testid="format-decimals"
              onChange={(e) => patchApp({ decimals: e.target.value as "number" | "string" })}
            >
              <option value="string">Exact text, e.g. &quot;12.50&quot; (recommended for money)</option>
              <option value="number">JSON numbers, e.g. 12.5</option>
            </select>
            <Hint>
              JSON numbers lose digits beyond about 15 significant figures. Exact text keeps every
              digit; callers convert it with their decimal type.
            </Hint>
          </label>
          <label>
            Time zone of stored date-times
            <input
              list="tz-list"
              value={tz}
              placeholder="UTC"
              spellCheck={false}
              data-testid="format-timezone"
              onChange={(e) =>
                setSpec((prev) => ({ ...prev, database: { ...prev.database, timezone: e.target.value || null } }))
              }
            />
            <datalist id="tz-list">
              {COMMON_ZONES.map((z) => (
                <option key={z} value={z} />
              ))}
            </datalist>
            <Hint>
              For columns without a time zone (MySQL DATETIME, SQL Server datetime2). Answers then
              include the offset, e.g. 2026-01-02T10:00:00+00:00. Leave empty to return them as stored.
            </Hint>
          </label>
        </div>
      </CardBody>
    </Card>
  );
}
