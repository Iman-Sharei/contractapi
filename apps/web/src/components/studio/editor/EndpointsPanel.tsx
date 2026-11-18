"use client";

import { tableKey } from "@/lib/tableKey";
import styles from "../studio.module.css";
import { type EditorState } from "./useEditorState";
import { ContractTab } from "./ContractTab";
import { PlayTab } from "./PlayTab";
import { RelationsTab } from "./RelationsTab";
import { SecurityTab } from "./SecurityTab";
import { SqlTab } from "./SqlTab";
import { YamlTab } from "./YamlTab";

export function EndpointsPanel({ s }: { s: EditorState }) {
  const { tables, setSelectedTable, spec, activeEndpoint, setActiveEndpoint, validation, editorTab, setEditorTab, pending, endpoint, removeEndpoint, onIntrospect, onValidate, onActivate } = s;
  return (
    <section className={styles.panelWide}>
      <div className={styles.panelHead}>
        <h2>Endpoints</h2>
        <div className={styles.rowGap}>
          <button type="button" className={styles.secondary} onClick={onValidate} disabled={pending}>
            Validate
          </button>
          <button type="button" className={styles.primary} onClick={onActivate} disabled={pending}>
            Activate
          </button>
        </div>
      </div>

      <div className={styles.endpointTabs}>
        {spec.endpoints.map((ep) => (
          <button
            key={ep.name}
            type="button"
            className={activeEndpoint === ep.name ? styles.tabActive : styles.tab}
            onClick={() => {
              setActiveEndpoint(ep.name);
              const t =
                tables.find((x) => x.schema === ep.schema && x.name === ep.table) ??
                tables.find((x) => x.name === ep.table);
              if (t) setSelectedTable(tableKey(t));
            }}
          >
            {ep.sql ? "Σ " : ""}
            {ep.path}
          </button>
        ))}
        {spec.endpoints.length === 0 && (
          <p className={styles.empty}>Add a table/view endpoint or a custom SQL endpoint.</p>
        )}
      </div>

      {!endpoint && spec.endpoints.length > 0 && (
        <div className={styles.emptyState}>
          <p>Select an endpoint tab above to edit its contract.</p>
          <button
            type="button"
            className={styles.primary}
            onClick={() => setActiveEndpoint(spec.endpoints[0]?.name ?? null)}
          >
            Open {spec.endpoints[0]?.path ?? "first endpoint"}
          </button>
        </div>
      )}

      {!endpoint && spec.endpoints.length === 0 && (
        <div className={styles.emptyState}>
          <p>
            No endpoints yet. Introspect the database on the left, pick a table, then add an
            endpoint — or use the New API wizard.
          </p>
          {tables.length === 0 && (
            <button type="button" className={styles.primary} onClick={onIntrospect} disabled={pending}>
              Introspect schema
            </button>
          )}
        </div>
      )}

      {endpoint && (
        <>
          <div className={styles.endpointTabs}>
            {(
              [
                ["contract", "Contract"],
                ["security", "Security"],
                ["relations", "Relations"],
                ["sql", "SQL"],
                ["play", "Try it"],
                ["yaml", "YAML"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={editorTab === id ? styles.tabActive : styles.tab}
                aria-pressed={editorTab === id}
                onClick={() => setEditorTab(id)}
              >
                {label}
              </button>
            ))}
            <button type="button" className={styles.dangerBtn} onClick={removeEndpoint}>
              Remove
            </button>
          </div>

          {editorTab === "contract" && <ContractTab s={s} />}

          {editorTab === "security" && <SecurityTab s={s} />}

          {editorTab === "relations" && <RelationsTab s={s} />}

          {editorTab === "sql" && <SqlTab s={s} />}

          {editorTab === "play" && <PlayTab s={s} />}

          {editorTab === "yaml" && <YamlTab s={s} />}
        </>
      )}

      {validation && (
        <div className={styles.validation}>
          <strong>{validation.valid ? "Valid" : "Invalid"}</strong>
          {validation.errors.map((e) => (
            <div key={e} className={styles.errLine}>
              {e}
            </div>
          ))}
          {validation.warnings.map((w) => (
            <div key={w} className={styles.warnLine}>
              {w}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
