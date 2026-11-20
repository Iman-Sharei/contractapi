"use client";

import { Icon } from "@/components/ui/Icon";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, cx } from "@/components/ui/primitives";
import { tableKey } from "@/lib/tableKey";
import type { TableInfo } from "@/lib/types";
import styles from "../pages.module.css";

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
  const pickedTables = p.tables.filter((t) => (p.pickedColumns[tableKey(t)]?.length ?? 0) > 0).length;
  const pickedCols = Object.values(p.pickedColumns).reduce((n, c) => n + c.length, 0);
  return (
    <Card data-testid="wizard-pick">
      <CardHeader
        icon="table"
        title="Choose what to share"
        description="Tick the tables to include, then open one to choose its columns. Columns that look private (passwords, tokens, keys) stay hidden."
        actions={
          <Badge tone={pickedTables ? "accent" : "neutral"}>
            {pickedTables} table{pickedTables === 1 ? "" : "s"} · {pickedCols} column
            {pickedCols === 1 ? "" : "s"}
          </Badge>
        }
      />
      <CardBody>
        {p.tables.length === 0 ? (
          <EmptyState icon="table" title="No tables found">
            Go back and check the connection and schema name.
          </EmptyState>
        ) : (
          <ul className={styles.tableCards}>
            {p.tables.map((t) => {
              const key = tableKey(t);
              const selected = p.pickedColumns[key] ?? [];
              const on = selected.length > 0;
              const open = p.expanded === key;
              return (
                <li key={key} className={cx(styles.tableCard, on && styles.tableCardOn)}>
                  <div className={styles.tableCardRow}>
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => p.toggleTable(key, t)}
                      aria-label={`Include ${t.name}`}
                    />
                    <button
                      type="button"
                      className={styles.tableCardBtn}
                      aria-expanded={open}
                      onClick={() => p.setExpanded(open ? null : key)}
                    >
                      <span className={styles.tableCardName}>
                        <Icon name="table" size={15} />
                        {t.name}
                        {t.kind === "view" && <Badge>view</Badge>}
                        {t.schema !== "public" && <Badge>{t.schema}</Badge>}
                      </span>
                      <span className={styles.tableCardMeta}>
                        {selected.length} of {t.columns.length} columns
                        {t.sensitive_columns.length > 0 && (
                          <>
                            {" · "}
                            <Icon name="lock" size={12} /> {t.sensitive_columns.length} private
                          </>
                        )}
                      </span>
                      <Icon name={open ? "chevronDown" : "chevronRight"} />
                    </button>
                  </div>
                  {open && (
                    <div className={styles.columnPanel}>
                      <div className={styles.columnPanelHead}>
                        <span>Columns in the response</span>
                        <Button size="sm" variant="ghost" onClick={() => p.selectAllColumns(key, t, true)}>
                          All safe columns
                        </Button>
                      </div>
                      <ul className={styles.columnGrid}>
                        {t.columns.map((c) => {
                          const checked = selected.includes(c.name);
                          const isPk = t.primary_keys.includes(c.name);
                          return (
                            <li key={c.name}>
                              <label className={cx(styles.columnItem, c.sensitive && styles.columnPrivate)}>
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  disabled={c.sensitive && !checked}
                                  onChange={() => {
                                    if (c.sensitive && !checked) return;
                                    p.toggleColumn(key, t, c.name);
                                  }}
                                />
                                <span className={styles.columnName}>
                                  {c.name}
                                  {isPk && <Badge tone="accent">unique id</Badge>}
                                  {c.sensitive && (
                                    <Badge tone="warning">
                                      <Icon name="lock" size={11} /> private, hidden
                                    </Badge>
                                  )}
                                </span>
                                <span className={styles.columnType}>{c.type.toLowerCase()}</span>
                              </label>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
      <div className={styles.cardFoot}>
        <Button variant="ghost" icon="arrowLeft" onClick={p.onBack}>
          Back
        </Button>
        <Button
          variant="primary"
          size="lg"
          icon="arrowRight"
          data-testid="wizard-pick-continue"
          disabled={!p.canContinue}
          onClick={p.onContinue}
        >
          Continue
        </Button>
      </div>
    </Card>
  );
}
