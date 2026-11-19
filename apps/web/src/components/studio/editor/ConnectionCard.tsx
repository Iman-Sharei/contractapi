"use client";

import { AUTH_OPTIONS, authHelp } from "@/lib/labels";
import type { ApiSpecDraft, DatabaseDriver } from "@/lib/types";
import styles from "../studio.module.css";
import { isWarehouseDriver, type EditorState } from "./useEditorState";

export function ConnectionCard({ s }: { s: EditorState }) {
  const { embedded, dbUrl, setDbUrl, dbDriver, schema, setSchema, tables, spec, specName, setSpecName, pending, showDbUrl, setShowDbUrl, patchApp, onIntrospect, onDriverChange, onSave, refreshSaved } = s;
  return (
    <section className={styles.settingsCard}>
      <div className={styles.settingsHead}>
        <h2>Database &amp; access</h2>
        <div className={styles.settingsActions}>
          <button type="button" className={styles.primary} onClick={onIntrospect} disabled={pending}>
            {tables.length === 0 ? "Load tables" : "Reload tables"}
          </button>
          <button type="button" className={styles.secondary} onClick={onSave} disabled={pending}>
            Save changes
          </button>
          {!embedded && (
            <button type="button" className={styles.secondary} onClick={refreshSaved}>
              Saved APIs
            </button>
          )}
        </div>
      </div>
      <div className={styles.fieldGrid}>
        <label>
          <span className={styles.fieldLabel}>Database type</span>
          <select
            value={dbDriver}
            onChange={(e) => onDriverChange(e.target.value as DatabaseDriver)}
          >
            <option value="postgres">Postgres</option>
            <option value="duckdb">DuckDB</option>
            <option value="snowflake">Snowflake</option>
            <option value="bigquery">BigQuery</option>
          </select>
        </label>
        <label className={styles.span2}>
          <span className={styles.fieldLabel}>
            {dbDriver === "postgres"
              ? "Connection URL"
              : dbDriver === "duckdb"
                ? "DuckDB URL"
                : dbDriver === "snowflake"
                  ? "Snowflake URL"
                  : "BigQuery URL"}
          </span>
          <div className={styles.inputWithBtn}>
            <input
              type={showDbUrl ? "text" : "password"}
              value={dbUrl}
              onChange={(e) => setDbUrl(e.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder={
                dbDriver === "duckdb"
                  ? "duckdb:///:memory: or duckdb:///./file.duckdb"
                  : dbDriver === "snowflake"
                    ? "snowflake://user:pass@account/db/schema"
                    : dbDriver === "bigquery"
                      ? "bigquery://project/dataset"
                      : undefined
              }
            />
            <button
              type="button"
              className={styles.ghostBtn}
              onClick={() => setShowDbUrl((v) => !v)}
              aria-pressed={showDbUrl}
            >
              {showDbUrl ? "Hide" : "Show"}
            </button>
          </div>
        </label>
        <label>
          <span className={styles.fieldLabel}>Schema</span>
          <input
            value={schema}
            onChange={(e) => setSchema(e.target.value)}
            disabled={dbDriver === "duckdb"}
          />
        </label>
        <label>
          <span className={styles.fieldLabel}>API name</span>
          <input value={specName} onChange={(e) => setSpecName(e.target.value)} />
        </label>
        <label>
          <span className={styles.fieldLabel}>Who can use it?</span>
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
          <span className={styles.hint}>{authHelp(spec.app.auth)}</span>
        </label>
        <label>
          <span className={styles.fieldLabel}>Version in the address (optional)</span>
          <input
            value={spec.app.api_prefix ?? ""}
            onChange={(e) => patchApp({ api_prefix: e.target.value })}
            placeholder="empty = no version"
            spellCheck={false}
          />
        </label>
      </div>
      {isWarehouseDriver(dbDriver) && (
        <p className={styles.hint}>
          {dbDriver === "duckdb" && (
            <>
              DuckDB is GA (<code>pip install &apos;contractapi[duckdb]&apos;</code>). Prefer SQL /
              aggregate endpoints. Table introspect stays Postgres-only.
            </>
          )}
          {dbDriver === "snowflake" && (
            <>
              Snowflake needs <code>pip install &apos;contractapi[snowflake]&apos;</code>. Define
              table/SQL endpoints with known fields.
            </>
          )}
          {dbDriver === "bigquery" && (
            <>
              BigQuery needs <code>pip install &apos;contractapi[bigquery]&apos;</code>. Define
              table/SQL endpoints with known fields.
            </>
          )}
        </p>
      )}
    </section>
  );
}
