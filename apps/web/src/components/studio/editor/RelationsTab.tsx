"use client";

import { tableKey } from "@/lib/tableKey";
import type { RelationDraft } from "@/lib/types";
import styles from "./editor.module.css";
import { slugify, type EditorState } from "./useEditorState";

export function RelationsTab({ s }: { s: EditorState }) {
  const { tables, endpoint, setStatus, addRelation, addManyToOne, updateRelation, toggleRelationField, removeRelation, parentTableName, childTables, parentForeignKeys } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
    <div className={styles.editorBlock}>
      {endpoint.sql ? (
        <p className={styles.empty}>SQL endpoints cannot nest relations.</p>
      ) : (
        <>
          <p className={styles.hint}>
            Nested arrays/objects in the JSON response. One-to-many: child table FK →{" "}
            <strong>{parentTableName ?? endpoint.table}</strong>. Many-to-one: parent FK
            → related table. Loaded in batch after Activate (no extra query param).
          </p>
          <pre className={styles.yaml}>
            {`{
  "id": "…",
  "email": "…",
  "orders": [ { "id": "…", "total": 42 } ],
  "account": { "id": "…", "name": "…" }
}`}
          </pre>
          <h3>Add one-to-many (nested array)</h3>
          <div className={styles.rowGap}>
            {childTables.map((c) => (
              <button
                key={tableKey(c)}
                type="button"
                className={styles.secondary}
                onClick={() => addRelation(c)}
              >
                + {c.schema}.{c.name}
              </button>
            ))}
            {childTables.length === 0 && (
              <span className={styles.empty}>
                No FK children found — introspect schema, or ensure{" "}
                <code>orders.customer_id → customers.id</code> exists.
              </span>
            )}
          </div>
          <h3>Add many-to-one (nested object)</h3>
          <div className={styles.rowGap}>
            {parentForeignKeys.map((fk) => (
              <button
                key={`${fk.column}-${fk.ref_table}`}
                type="button"
                className={styles.secondary}
                onClick={() => addManyToOne(fk)}
              >
                + {fk.column} → {fk.ref_table}
              </button>
            ))}
            {parentForeignKeys.length === 0 && (
              <span className={styles.empty}>
                No outbound FKs on this table.
              </span>
            )}
          </div>
          <h3>Active relations</h3>
          {(endpoint.relations ?? []).length === 0 && (
            <p className={styles.empty}>No nested relations yet.</p>
          )}
          {(endpoint.relations ?? []).map((r) => {
            const relTable =
              tables.find((t) => t.name === r.table && t.schema === r.schema) ??
              tables.find((t) => t.name === r.table);
            const relCols = relTable?.columns.map((c) => c.name) ?? r.fields;
            return (
              <div key={r.name} className={styles.relCard}>
                <div className={styles.settingsHead}>
                  <code>
                    {r.name}
                    {r.type === "one_to_many" ? "[]" : ""} ← {r.schema}.{r.table}
                  </code>
                  <button
                    type="button"
                    className={styles.dangerBtn}
                    aria-label={`Remove relation ${r.name}`}
                    onClick={() => removeRelation(r.name)}
                  >
                    ×
                  </button>
                </div>
                <div className={styles.twoCol}>
                  <label>
                    Name
                    <input
                      value={r.name}
                      onChange={(e) => {
                        const next = slugify(e.target.value);
                        if (!next) return;
                        if (
                          next !== r.name &&
                          (endpoint.relations ?? []).some((x) => x.name === next)
                        ) {
                          setStatus(null, `Relation '${next}' already exists.`);
                          return;
                        }
                        updateRelation(r.name, { name: next });
                      }}
                    />
                  </label>
                  <label>
                    Type
                    <select
                      value={r.type}
                      onChange={(e) =>
                        updateRelation(r.name, {
                          type: e.target.value as RelationDraft["type"],
                          max_per_parent:
                            e.target.value === "many_to_one"
                              ? 1
                              : Math.max(r.max_per_parent, 2),
                        })
                      }
                    >
                      <option value="one_to_many">one_to_many</option>
                      <option value="many_to_one">many_to_one</option>
                    </select>
                  </label>
                </div>
                <div className={styles.twoCol}>
                  <label>
                    Local key
                    <input
                      value={r.local_key}
                      onChange={(e) =>
                        updateRelation(r.name, { local_key: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Foreign key
                    <input
                      value={r.foreign_key}
                      onChange={(e) =>
                        updateRelation(r.name, { foreign_key: e.target.value })
                      }
                    />
                  </label>
                </div>
                <label>
                  Hide deleted rows (optional column)
                  <input
                    value={r.soft_delete_column ?? ""}
                    placeholder="deleted_at"
                    onChange={(e) =>
                      updateRelation(r.name, {
                        soft_delete_column: e.target.value.trim() || null,
                      })
                    }
                  />
                  <span className={styles.hint}>
                    Nested rows where this column has a value are left out.
                  </span>
                </label>
                <div className={styles.twoCol}>
                  <label>
                    Primary key
                    <input
                      value={r.primary_key}
                      onChange={(e) =>
                        updateRelation(r.name, { primary_key: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Max per parent
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={r.max_per_parent}
                      disabled={r.type === "many_to_one"}
                      onChange={(e) =>
                        updateRelation(r.name, {
                          max_per_parent: Math.min(
                            500,
                            Math.max(1, Number(e.target.value) || 1),
                          ),
                        })
                      }
                    />
                  </label>
                </div>
                <p className={styles.hint}>Fields returned on the nested resource</p>
                <div className={styles.toggleRow}>
                  {relCols.map((f) => (
                    <label key={f} className={styles.check}>
                      <input
                        type="checkbox"
                        checked={r.fields.includes(f)}
                        onChange={() => toggleRelationField(r.name, f)}
                      />
                      {f}
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
    </>
  );
}
