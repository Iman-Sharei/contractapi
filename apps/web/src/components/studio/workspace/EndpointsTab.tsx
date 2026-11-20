"use client";

import { Icon } from "@/components/ui/Icon";
import { useConfirm } from "@/components/ui/feedback";
import { Banner, Button, Card, EmptyState, Method, Tabs, cx } from "@/components/ui/primitives";
import { formatApiPath } from "@/lib/pickColumns";
import { tableKey } from "@/lib/tableKey";
import { ContractTab } from "../editor/ContractTab";
import { PlayTab } from "../editor/PlayTab";
import { RelationsTab } from "../editor/RelationsTab";
import { SecurityTab } from "../editor/SecurityTab";
import { SqlTab } from "../editor/SqlTab";
import type { EditorState } from "../editor/useEditorState";
import styles from "../pages.module.css";

type Sub = "contract" | "security" | "relations" | "sql" | "play";

/** Endpoint list on the left, the selected endpoint's editor on the right. */
export function EndpointsTab({ s }: { s: EditorState }) {
  const {
    tables,
    selectedTable,
    setSelectedTable,
    selected,
    spec,
    activeEndpoint,
    setActiveEndpoint,
    endpoint,
    editorTab,
    setEditorTab,
    validation,
    pending,
    onIntrospect,
    addEndpointFromTable,
    addSqlEndpoint,
    removeEndpoint,
    onValidate,
  } = s;
  const confirm = useConfirm();
  const sub: Sub = editorTab === "yaml" ? "contract" : editorTab;
  const prefix = spec.app.api_prefix ?? "";

  function open(name: string) {
    setActiveEndpoint(name);
    const ep = spec.endpoints.find((e) => e.name === name);
    const t =
      tables.find((x) => x.schema === ep?.schema && x.name === ep?.table) ??
      tables.find((x) => x.name === ep?.table);
    if (t) setSelectedTable(tableKey(t));
  }

  async function onRemove() {
    if (!endpoint) return;
    const ok = await confirm({
      title: `Remove endpoint '${endpoint.name}'?`,
      body: "It disappears from the API the next time you save and make it live.",
      confirmLabel: "Remove endpoint",
    });
    if (ok) removeEndpoint();
  }

  return (
    <div className={styles.endpointsLayout}>
      <aside className={styles.rail} aria-label="Endpoints">
        <div className={styles.railHead}>
          <span>Endpoints</span>
          <span className={styles.muted}>{spec.endpoints.length}</span>
        </div>
        <ul className={styles.railList}>
          {spec.endpoints.map((ep) => (
            <li key={ep.name}>
              <button
                type="button"
                className={cx(styles.railItem, activeEndpoint === ep.name && styles.railItemOn)}
                aria-current={activeEndpoint === ep.name ? "true" : undefined}
                onClick={() => open(ep.name)}
              >
                <span className={styles.railPath}>
                  {ep.sql || ep.aggregate ? <Icon name="code" size={13} /> : <Icon name="table" size={13} />}
                  {formatApiPath(prefix, ep.path)}
                </span>
                <span className={styles.railMethods}>
                  {(ep.sql || ep.aggregate ? ["GET"] : ep.methods).map((m) => (
                    <span key={m} className={cx(styles.methodDot, styles[`m${m}`])} title={m} />
                  ))}
                </span>
              </button>
            </li>
          ))}
          {spec.endpoints.length === 0 && <li className={styles.railEmpty}>No endpoints yet.</li>}
        </ul>

        <div className={styles.railAdd}>
          <span className={styles.reviewLabel}>Add an endpoint</span>
          {tables.length > 0 ? (
            <>
              <label>
                From a table
                <select value={selectedTable ?? ""} onChange={(e) => setSelectedTable(e.target.value)}>
                  {tables.map((t) => (
                    <option key={tableKey(t)} value={tableKey(t)}>
                      {t.name}
                      {t.kind === "view" ? " (view)" : ""}
                      {t.sensitive_columns.length ? ` · ${t.sensitive_columns.length} private` : ""}
                    </option>
                  ))}
                </select>
              </label>
              {selected && (
                <Button size="sm" variant="secondary" icon="plus" onClick={() => addEndpointFromTable(selected)}>
                  Add an endpoint for {selected.name}
                </Button>
              )}
            </>
          ) : (
            <Button size="sm" variant="secondary" icon="database" onClick={onIntrospect} disabled={pending}>
              Load tables
            </Button>
          )}
          <Button size="sm" variant="ghost" icon="code" onClick={addSqlEndpoint}>
            Add a custom query (SQL)
          </Button>
        </div>
      </aside>

      <Card className={styles.editorCard}>
        {!endpoint ? (
          <div className={styles.editorEmpty}>
            {spec.endpoints.length > 0 ? (
              <EmptyState
                icon="layers"
                title="Pick an endpoint"
                action={
                  <Button variant="primary" onClick={() => open(spec.endpoints[0].name)}>
                    Open {spec.endpoints[0].path}
                  </Button>
                }
              >
                Choose an endpoint on the left to change its fields, access and paging.
              </EmptyState>
            ) : (
              <EmptyState icon="plus" title="No endpoints yet">
                Load your tables on the left and add one, or add a custom SQL query.
              </EmptyState>
            )}
          </div>
        ) : (
          <>
            <div className={styles.editorHead}>
              <div style={{ minWidth: 0 }}>
                <h2 className={styles.editorTitle}>
                  {!endpoint.sql && !endpoint.aggregate && endpoint.methods.map((m) => <Method key={m} method={m} />)}
                  <code>{formatApiPath(prefix, endpoint.path)}</code>
                </h2>
                <p className={styles.editorSub}>
                  {endpoint.sql ? "Custom SQL query" : endpoint.aggregate ? "Totals over" : "Rows from"}{" "}
                  {!endpoint.sql && <code>{endpoint.aggregate?.table ?? endpoint.table}</code>}
                </p>
              </div>
              <div className={styles.editorActions}>
                <Button size="sm" variant="secondary" icon="checkCircle" onClick={onValidate} disabled={pending}>
                  Check for problems
                </Button>
                <Button size="sm" variant="ghost" icon="trash" onClick={onRemove}>
                  Remove
                </Button>
              </div>
            </div>
            <Tabs
              label="Endpoint settings"
              value={sub}
              onChange={setEditorTab}
              className={styles.editorTabs}
              items={[
                { id: "contract", label: "Fields & paging" },
                { id: "security", label: "Access & rules" },
                { id: "relations", label: "Relations" },
                { id: "sql", label: "SQL & totals" },
                { id: "play", label: "Try it" },
              ]}
            />
            <div className={styles.editorBody}>
              {sub === "contract" && <ContractTab s={s} />}
              {sub === "security" && <SecurityTab s={s} />}
              {sub === "relations" && <RelationsTab s={s} />}
              {sub === "sql" && <SqlTab s={s} />}
              {sub === "play" && <PlayTab s={s} />}

              {validation && (
                <Banner
                  tone={validation.valid ? (validation.warnings.length ? "warning" : "success") : "danger"}
                  role="status"
                >
                  <strong>{validation.valid ? "No blocking problems." : "Fix these before publishing:"}</strong>
                  {[...validation.errors, ...validation.warnings].length > 0 && (
                    <ul className={styles.validationList}>
                      {validation.errors.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                      {validation.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  )}
                </Banner>
              )}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
