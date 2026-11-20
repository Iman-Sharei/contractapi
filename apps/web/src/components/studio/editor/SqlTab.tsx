"use client";

import styles from "./editor.module.css";
import { type EditorState } from "./useEditorState";

export function SqlTab({ s }: { s: EditorState }) {
  const { pending, sqlDraft, setSqlDraft, selected, endpoint, setStatus, updateEndpoint, onDiscoverSql } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
    <div className={styles.editorBlock}>
      <p className={styles.hint}>
        Use raw SQL <em>or</em> Aggregation DSL (GROUP BY metrics). Writes and relations
        are disabled for both.
      </p>
      <h3>Aggregation DSL</h3>
      <p className={styles.hint}>
        Prefer this for count/sum/avg without writing SQL. Clears raw SQL when applied.
      </p>
      <div className={styles.twoCol}>
        <label>
          Table
          <input
            value={endpoint.aggregate?.table ?? selected?.name ?? endpoint.table ?? ""}
            onChange={(e) =>
              updateEndpoint({
                aggregate: {
                  table: e.target.value,
                  schema:
                    endpoint.aggregate?.schema ??
                    selected?.schema ??
                    endpoint.schema ??
                    "public",
                  group_by: endpoint.aggregate?.group_by ?? [],
                  metrics: endpoint.aggregate?.metrics ?? [
                    { name: "row_count", op: "count" },
                  ],
                },
                sql: null,
              })
            }
            placeholder="orders"
          />
        </label>
        <label>
          Schema
          <input
            value={endpoint.aggregate?.schema ?? endpoint.schema ?? "public"}
            onChange={(e) =>
              updateEndpoint({
                aggregate: {
                  table:
                    endpoint.aggregate?.table ??
                    selected?.name ??
                    endpoint.table ??
                    "table",
                  schema: e.target.value,
                  group_by: endpoint.aggregate?.group_by ?? [],
                  metrics: endpoint.aggregate?.metrics ?? [
                    { name: "row_count", op: "count" },
                  ],
                },
                sql: null,
              })
            }
          />
        </label>
      </div>
      <label>
        Group by (comma-separated)
        <input
          value={(endpoint.aggregate?.group_by ?? []).join(", ")}
          onChange={(e) => {
            const group_by = e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);
            updateEndpoint({
              aggregate: {
                table:
                  endpoint.aggregate?.table ??
                  selected?.name ??
                  endpoint.table ??
                  "table",
                schema:
                  endpoint.aggregate?.schema ??
                  selected?.schema ??
                  endpoint.schema ??
                  "public",
                group_by,
                metrics: endpoint.aggregate?.metrics ?? [
                  { name: "row_count", op: "count" },
                ],
              },
              sql: null,
              pagination: {
                enabled: true,
                mode: "offset",
                default_limit: endpoint.pagination?.default_limit ?? 50,
                max_limit: endpoint.pagination?.max_limit ?? 200,
              },
            });
          }}
          placeholder="status, customer_id"
        />
      </label>
      <label>
        Metrics YAML-ish (name:op[:field] per line)
        <textarea
          className={styles.sqlBox}
          rows={3}
          value={(endpoint.aggregate?.metrics ?? [])
            .map((m) =>
              m.field ? `${m.name}:${m.op}:${m.field}` : `${m.name}:${m.op}`,
            )
            .join("\n")}
          onChange={(e) => {
            const metrics = e.target.value
              .split("\n")
              .map((ln) => ln.trim())
              .filter(Boolean)
              .map((ln) => {
                const [name, op, field] = ln.split(":").map((s) => s.trim());
                return {
                  name: name || "metric",
                  op: (op || "count") as "count" | "sum" | "avg" | "min" | "max",
                  field: field || null,
                };
              });
            updateEndpoint({
              aggregate: {
                table:
                  endpoint.aggregate?.table ??
                  selected?.name ??
                  endpoint.table ??
                  "table",
                schema:
                  endpoint.aggregate?.schema ??
                  selected?.schema ??
                  endpoint.schema ??
                  "public",
                group_by: endpoint.aggregate?.group_by ?? [],
                metrics: metrics.length
                  ? metrics
                  : [{ name: "row_count", op: "count" }],
              },
              sql: null,
            });
          }}
          placeholder={"order_count:count\nrevenue:sum:amount"}
        />
      </label>
      <button
        type="button"
        className={styles.secondary}
        onClick={() => {
          updateEndpoint({ aggregate: null });
          setStatus("Cleared aggregation DSL — use raw SQL below if needed.");
        }}
      >
        Clear aggregation
      </button>

      <h3>Raw SQL</h3>
      <textarea
        className={styles.sqlBox}
        value={endpoint.aggregate ? "" : endpoint.sql ?? sqlDraft}
        disabled={!!endpoint.aggregate}
        onChange={(e) => {
          setSqlDraft(e.target.value);
          updateEndpoint({ sql: e.target.value, aggregate: null });
        }}
        rows={10}
        spellCheck={false}
        placeholder={
          endpoint.aggregate
            ? "(disabled while Aggregation DSL is set)"
            : "SELECT …"
        }
      />
      <div className={styles.rowGap}>
        <button
          type="button"
          className={styles.primary}
          onClick={onDiscoverSql}
          disabled={pending || !!endpoint.aggregate}
        >
          Discover columns
        </button>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            const table = selected?.name ?? endpoint.table;
            if (!table || table === "_sql") {
              setStatus(null, "Select a table before converting from SQL.");
              return;
            }
            updateEndpoint({
              sql: null,
              aggregate: null,
              table,
              schema: selected?.schema ?? endpoint.schema,
            });
            setStatus(`Converted to table endpoint on ${table}.`);
          }}
        >
          Convert to table endpoint
        </button>
      </div>
      <h3>SQL params</h3>
      <p className={styles.hint}>
        Bind <code>:name</code> placeholders. Example:{" "}
        <code>name=min_total,type=float,default=0</code>
      </p>
      <textarea
        className={styles.sqlBox}
        rows={3}
        value={(endpoint.sql_params ?? [])
          .map(
            (p) =>
              `${p.name},type=${p.type}${p.required ? ",required" : ""}${
                p.default != null && p.default !== "" ? `,default=${p.default}` : ""
              }`,
          )
          .join("\n")}
        onChange={(e) => {
          const params = e.target.value
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line) => {
              const parts = line.split(",").map((x) => x.trim());
              const name = parts[0]?.replace(/^name=/, "") || "param";
              const typePart = parts.find((p) => p.startsWith("type="))?.slice(5) || "string";
              const defPart = parts.find((p) => p.startsWith("default="))?.slice(8);
              const required = parts.includes("required");
              const type = (["string", "int", "float", "bool"].includes(typePart)
                ? typePart
                : "string") as "string" | "int" | "float" | "bool";
              let def: string | number | boolean | null = defPart ?? null;
              if (defPart != null && type === "int") def = Number(defPart);
              if (defPart != null && type === "float") def = Number(defPart);
              if (defPart != null && type === "bool") def = ["1", "true", "yes"].includes(defPart.toLowerCase());
              return { name, type, required, default: def };
            });
          updateEndpoint({ sql_params: params });
        }}
        spellCheck={false}
      />
      <label className={styles.check}>
        <input
          type="checkbox"
          checked={endpoint.ndjson_export ?? true}
          onChange={(e) => updateEndpoint({ ndjson_export: e.target.checked })}
        />
        NDJSON export
      </label>
    </div>
    </>
  );
}
