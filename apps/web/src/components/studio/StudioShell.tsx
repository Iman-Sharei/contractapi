"use client";

import { getApiBase } from "@/lib/api";
import { tableKey } from "@/lib/tableKey";
import styles from "./studio.module.css";
import { useEditorState } from "./editor/useEditorState";
import { ApiSurfaceCard } from "./editor/ApiSurfaceCard";
import { ConnectionCard } from "./editor/ConnectionCard";
import { EndpointsPanel } from "./editor/EndpointsPanel";

export function StudioShell(props: { initialName?: string; embedded?: boolean }) {
  const s = useEditorState(props);
  const { embedded, tables, selectedTable, setSelectedTable, savedNames, message, error, yamlText, pending, dirty, contractOpen, setContractOpen, selected, localYaml, onCopy, onIntrospect, addEndpointFromTable, addSqlEndpoint, onLoad } = s;
  return (
    <div
      className={styles.shell}
      style={embedded ? { maxWidth: "none", padding: 0 } : undefined}
      aria-busy={pending || undefined}
    >
      {!embedded && (
        <div className={styles.topActions} style={{ marginBottom: 12 }}>
          <span className={styles.pill}>{pending ? "Working…" : dirty ? "Unsaved" : "Editor"}</span>
          <a className={styles.linkBtn} href={`${getApiBase()}/data/docs`} target="_blank" rel="noreferrer">
            Live /data docs
          </a>
          <a
            className={styles.linkBtn}
            href={`${getApiBase()}/data/graphql`}
            target="_blank"
            rel="noreferrer"
            title="Requires pip install 'contractapi[graphql]'. Reads: table + SQL GETs. Mutations: table POST/PATCH/DELETE."
          >
            GraphQL
          </a>
        </div>
      )}

      <ConnectionCard s={s} />

      <ApiSurfaceCard s={s} />

      {savedNames.length > 0 && (
        <div className={styles.endpointTabs}>
          {savedNames.map((name) => (
            <button key={name} type="button" className={styles.tab} onClick={() => onLoad(name)}>
              load:{name}
            </button>
          ))}
        </div>
      )}

      {(message || error) && (
        <div
          className={error ? styles.bannerError : styles.bannerOk}
          role={error ? "alert" : "status"}
        >
          {error ?? message}
        </div>
      )}

      <div className={contractOpen ? styles.grid : styles.gridYamlCollapsed}>
        <aside className={styles.panel}>
          <div className={styles.panelHead}>
            <h2>Tables</h2>
            <span>{tables.length}</span>
          </div>
          <ul className={styles.tableList}>
            {tables.map((t) => (
              <li key={tableKey(t)}>
                <button
                  type="button"
                  className={selectedTable === tableKey(t) ? styles.tableActive : styles.tableBtn}
                  onClick={() => setSelectedTable(tableKey(t))}
                >
                  <span>
                    {t.name}
                    {t.kind === "view" ? " · view" : ""}
                  </span>
                  {t.sensitive_columns.length > 0 && (
                    <em title="Sensitive columns">{t.sensitive_columns.length}</em>
                  )}
                </button>
              </li>
            ))}
            {tables.length === 0 && (
              <li className={styles.empty}>Press “Load tables” to see your database.</li>
            )}
          </ul>
          <div className={styles.stackBtns}>
            {selected && (
              <button
                type="button"
                className={styles.secondary}
                onClick={() => addEndpointFromTable(selected)}
              >
                Add an endpoint for {selected.name}
              </button>
            )}
            {tables.length === 0 && (
              <button type="button" className={styles.secondary} onClick={onIntrospect} disabled={pending}>
                Load tables
              </button>
            )}
            <button type="button" className={styles.secondary} onClick={addSqlEndpoint}>
              Add a custom query (SQL)
            </button>
          </div>
        </aside>

        <EndpointsPanel s={s} />

        <aside className={contractOpen ? styles.panel : styles.panelCollapsed}>
          <div className={styles.panelHead}>
            <h2>API file</h2>
            <div className={styles.rowGap}>
              <button
                type="button"
                className={styles.ghostBtn}
                aria-expanded={contractOpen}
                onClick={() => setContractOpen((v) => !v)}
              >
                {contractOpen ? "Hide file" : "Show file"}
              </button>
              {contractOpen && (
                <button
                  type="button"
                  className={styles.ghostBtn}
                  onClick={() => onCopy(yamlText || localYaml, "YAML")}
                >
                  Copy
                </button>
              )}
            </div>
          </div>
          {contractOpen && <pre className={styles.yaml}>{yamlText || localYaml}</pre>}
          {!contractOpen && (
            <p className={styles.empty}>The whole API as a YAML file — open it to review or copy.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
