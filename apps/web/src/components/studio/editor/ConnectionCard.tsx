"use client";

import { Button, Card, CardBody, CardHeader, Hint, ui } from "@/components/ui/primitives";
import { AUTH_OPTIONS, authHelp } from "@/lib/labels";
import type { ApiSpecDraft, DatabaseDriver } from "@/lib/types";
import { isWarehouseDriver, type EditorState } from "./useEditorState";
import styles from "./editor.module.css";

const URL_LABEL: Record<DatabaseDriver, string> = {
  postgres: "Connection URL",
  mysql: "Connection URL",
  sqlserver: "Connection URL",
  duckdb: "DuckDB URL",
  snowflake: "Snowflake URL",
  bigquery: "BigQuery URL",
};

const URL_PLACEHOLDER: Partial<Record<DatabaseDriver, string>> = {
  postgres: "postgresql://user:password@host:5432/database",
  mysql: "mysql://user:password@host:3306/database",
  sqlserver: "mssql://user:password@host:1433/database",
  duckdb: "duckdb:///:memory: or duckdb:///./file.duckdb",
  snowflake: "snowflake://user:pass@account/db/schema",
  bigquery: "bigquery://project/dataset",
};

export function ConnectionCard({ s }: { s: EditorState }) {
  const { dbUrl, setDbUrl, dbDriver, schema, setSchema, tables, spec, pending, showDbUrl, setShowDbUrl, patchApp, onIntrospect, onDriverChange } = s;
  return (
    <Card>
      <CardHeader
        icon="database"
        title="Database & access"
        description="Where the data comes from, and who may call the API."
        actions={
          <Button size="sm" variant="secondary" icon="refresh" onClick={onIntrospect} disabled={pending}>
            {tables.length === 0 ? "Load tables" : "Reload tables"}
          </Button>
        }
      />
      <CardBody className={ui.stack}>
        <div className={styles.fieldGrid}>
          <label>
            Database type
            <select value={dbDriver} onChange={(e) => onDriverChange(e.target.value as DatabaseDriver)}>
              <option value="postgres">PostgreSQL</option>
              <option value="mysql">MySQL</option>
              <option value="sqlserver">SQL Server</option>
              <option value="duckdb">DuckDB</option>
              <option value="snowflake">Snowflake</option>
              <option value="bigquery">BigQuery</option>
            </select>
          </label>
          <label className={styles.span2}>
            {URL_LABEL[dbDriver]}
            <div className={styles.inputWithBtn}>
              <input
                type={showDbUrl ? "text" : "password"}
                value={dbUrl}
                onChange={(e) => setDbUrl(e.target.value)}
                spellCheck={false}
                autoComplete="off"
                placeholder={URL_PLACEHOLDER[dbDriver]}
              />
              <Button variant="secondary" onClick={() => setShowDbUrl((v) => !v)} aria-pressed={showDbUrl}>
                {showDbUrl ? "Hide" : "Show"}
              </Button>
            </div>
          </label>
          <label>
            Schema
            <input value={schema} onChange={(e) => setSchema(e.target.value)} disabled={dbDriver === "duckdb"} />
            {dbDriver === "mysql" && <Hint>On MySQL this is the database name.</Hint>}
            {dbDriver === "sqlserver" && <Hint>Usually dbo.</Hint>}
          </label>
          <label>
            Who can use it?
            <select
              value={spec.app.auth}
              onChange={(e) => patchApp({ auth: e.target.value as ApiSpecDraft["app"]["auth"] })}
            >
              {AUTH_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <Hint>{authHelp(spec.app.auth)}</Hint>
          </label>
          <label>
            Version in the address (optional)
            <input
              value={spec.app.api_prefix ?? ""}
              onChange={(e) => patchApp({ api_prefix: e.target.value })}
              placeholder="empty = no version, e.g. /v1"
              spellCheck={false}
            />
          </label>
        </div>
        {isWarehouseDriver(dbDriver) && (
          <Hint>
            {dbDriver === "duckdb" && (
              <>
                DuckDB needs <code>pip install &apos;contractapi[duckdb]&apos;</code>. Prefer SQL / totals
                endpoints; loading tables works for Postgres only.
              </>
            )}
            {dbDriver === "snowflake" && (
              <>
                Snowflake needs <code>pip install &apos;contractapi[snowflake]&apos;</code>. Define table
                or SQL endpoints with known fields.
              </>
            )}
            {dbDriver === "bigquery" && (
              <>
                BigQuery needs <code>pip install &apos;contractapi[bigquery]&apos;</code>. Define table
                or SQL endpoints with known fields.
              </>
            )}
          </Hint>
        )}
      </CardBody>
    </Card>
  );
}
