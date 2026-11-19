"use client";

import { tableKey } from "@/lib/tableKey";
import type { TableInfo } from "@/lib/types";
import styles from "../flow.module.css";

type Props = {
  tables: TableInfo[];
  pickedColumns: Record<string, string[]>;
  expanded: string | null;
  setExpanded: (key: string | null) => void;
  toggleTable: (key: string, table: TableInfo) => void;
  toggleColumn: (key: string, table: TableInfo, col: string) => void;
  selectAllColumns: (key: string, table: TableInfo, safeOnly: boolean) => void;
  canContinue: boolean;
  onBack: () => void;
  onContinue: () => void;
};

/** Step 2 — choose which tables and columns the API shares. */
export function PickStep(p: Props) {
  return (
    <section className={styles.panel} data-testid="wizard-pick">
      <h2>Choose what to share</h2>
      <p>
        Tick the tables to include, then open one to choose its columns. Columns that look private
        (passwords, tokens, keys) stay hidden.
      </p>
      <div className={styles.sourceList}>
        {p.tables.map((t) => {
          const key = tableKey(t);
          const selected = p.pickedColumns[key] ?? [];
          const on = selected.length > 0;
          const open = p.expanded === key;
          return (
            <div key={key} className={styles.sourceCard}>
              <div className={styles.sourceRow}>
                <button
                  type="button"
                  className={styles.sourceExpand}
                  aria-expanded={open}
                  onClick={() => p.setExpanded(open ? null : key)}
                >
                  <span aria-hidden>{open ? "▾" : "▸"}</span>
                  <strong>{t.name}</strong>
                  <span className={styles.sourceMeta}>
                    {selected.length} of {t.columns.length} columns
                    {t.schema !== "public" ? ` · ${t.schema}` : ""}
                  </span>
                </button>
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => p.toggleTable(key, t)}
                  aria-label={`Include ${t.name}`}
                />
              </div>
              {open && (
                <div className={styles.columnPicker}>
                  <div className={styles.columnToolbar}>
                    <button
                      type="button"
                      className={styles.ghost}
                      onClick={() => p.selectAllColumns(key, t, true)}
                    >
                      All safe columns
                    </button>
                  </div>
                  <ul className={styles.columnList}>
                    {t.columns.map((c) => {
                      const checked = selected.includes(c.name);
                      const isPk = t.primary_keys.includes(c.name);
                      return (
                        <li key={c.name}>
                          <label className={c.sensitive ? styles.columnRowSensitive : styles.columnRow}>
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={c.sensitive && !checked}
                              onChange={() => {
                                if (c.sensitive && !checked) return;
                                p.toggleColumn(key, t, c.name);
                              }}
                            />
                            <span>
                              {c.name}
                              {isPk ? " · unique id" : ""}
                              {c.sensitive ? " · private, hidden" : ""}
                            </span>
                            <em>{c.type.toLowerCase()}</em>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
        {p.tables.length === 0 && <p>No tables found — go back and check the connection.</p>}
      </div>
      <div className={styles.toolbar}>
        <button type="button" className={styles.ghost} onClick={p.onBack}>
          Back
        </button>
        <button
          type="button"
          className={styles.primary}
          data-testid="wizard-pick-continue"
          disabled={!p.canContinue}
          onClick={p.onContinue}
        >
          Continue
        </button>
      </div>
    </section>
  );
}
