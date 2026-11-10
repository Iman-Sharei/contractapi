"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import {
  activateSpec,
  introspectDatabase,
  saveSpec,
  validateSpec,
} from "@/lib/api";
import { defaultSafeColumns, ensurePrimaryKey, formatApiPath } from "@/lib/pickColumns";
import { tableKey } from "@/lib/tableKey";
import type { ApiSpecDraft, EndpointDraft, TableInfo } from "@/lib/types";
import { ALL_FILTER_OPS } from "@/lib/types";
import styles from "@/components/studio/flow.module.css";

const STEPS = ["Connect", "Pick", "Guards"] as const;

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "resource";
}

function uniqueEndpointName(base: string, used: Set<string>): string {
  let name = slugify(base);
  let i = 2;
  while (used.has(name)) name = `${slugify(base)}_${i++}`;
  used.add(name);
  return name;
}

export default function NewApiWizardPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [specName, setSpecName] = useState("my_api");
  const [dbUrl, setDbUrl] = useState("postgresql://postgres:postgres@db:5432/app");
  const [showPass, setShowPass] = useState(false);
  const [schema, setSchema] = useState("public");
  const [tables, setTables] = useState<TableInfo[]>([]);
  /** tableKey → selected column names */
  const [pickedColumns, setPickedColumns] = useState<Record<string, string[]>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [auth, setAuth] = useState<ApiSpecDraft["app"]["auth"]>("api_key");
  const [readOnly, setReadOnly] = useState(true);
  const [title, setTitle] = useState("My Data API");
  const [apiPrefix, setApiPrefix] = useState("");

  const pickedKeys = useMemo(
    () => Object.keys(pickedColumns).filter((k) => (pickedColumns[k]?.length ?? 0) > 0),
    [pickedColumns],
  );

  const draft = useMemo((): ApiSpecDraft => {
    const used = new Set<string>();
    const endpoints: EndpointDraft[] = [];
    for (const key of pickedKeys) {
      const table = tables.find((t) => tableKey(t) === key);
      if (!table) continue;
      const name = uniqueEndpointName(table.name, used);
      const pk = table.primary_keys[0] ?? table.columns.find((c) => !c.sensitive)?.name ?? "id";
      const fields = ensurePrimaryKey(pickedColumns[key] ?? [], table);
      if (fields.length === 0) continue;
      endpoints.push({
        name,
        path: `/${name}`,
        table: table.name,
        schema: table.schema,
        methods: ["GET"],
        primary_key: pk,
        fields,
        writable_fields: fields.filter((f) => f !== pk),
        filters: fields.filter((f) => f !== pk).slice(0, 3),
        filter_operators: [...ALL_FILTER_OPS],
        sortable: [pk],
        pagination: { enabled: true, mode: "cursor", default_limit: 20, max_limit: 100 },
        csv_export: true,
        description: `Generated from ${table.kind ?? "table"} ${table.schema}.${table.name}`,
      });
    }
    return {
      database: { url: dbUrl },
      app: {
        title,
        version: "0.1.0",
        description: "Created with contractapi Studio wizard",
        read_only: readOnly,
        auth,
        api_prefix: apiPrefix,
        cache: { enabled: true, ttl_seconds: 30 },
        idempotency: { enabled: true, required_for_writes: false, ttl_seconds: 86400 },
        rate_limit: { enabled: true, requests_per_minute: 120 },
        audit_enabled: true,
        compression: true,
        tracing: true,
      },
      endpoints,
    };
  }, [pickedKeys, pickedColumns, tables, dbUrl, title, readOnly, auth, apiPrefix]);

  function goStep(i: number) {
    if (i > 0 && tables.length === 0) {
      setError("Connect and introspect the database first.");
      return;
    }
    if (i > 1 && pickedKeys.length === 0) {
      setError("Pick at least one table and one column.");
      return;
    }
    setError(null);
    setStep(i);
  }

  function onIntrospect() {
    setError(null);
    if (!dbUrl.trim()) {
      setError("Database URL is required.");
      return;
    }
    startTransition(async () => {
      try {
        const result = await introspectDatabase(dbUrl, schema);
        setTables(result.tables);
        const next: Record<string, string[]> = {};
        for (const t of result.tables) {
          next[tableKey(t)] = defaultSafeColumns(t);
        }
        setPickedColumns(next);
        setExpanded(result.tables[0] ? tableKey(result.tables[0]) : null);
        setMessage(`Found ${result.count} tables/views — choose columns to expose.`);
        setStep(1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Introspect failed");
      }
    });
  }

  function toggleTable(key: string, table: TableInfo) {
    setPickedColumns((prev) => {
      if ((prev[key]?.length ?? 0) > 0) {
        const rest = { ...prev };
        delete rest[key];
        return rest;
      }
      return { ...prev, [key]: defaultSafeColumns(table) };
    });
    setExpanded(key);
  }

  function toggleColumn(key: string, table: TableInfo, col: string) {
    const pk = table.primary_keys[0];
    setPickedColumns((prev) => {
      const cur = prev[key] ?? [];
      if (cur.includes(col)) {
        if (col === pk && cur.length <= 1) return prev;
        if (col === pk) return { ...prev, [key]: cur.filter((c) => c !== col) };
        const next = cur.filter((c) => c !== col);
        if (next.length === 0) {
          const rest = { ...prev };
          delete rest[key];
          return rest;
        }
        return { ...prev, [key]: next };
      }
      return { ...prev, [key]: ensurePrimaryKey([...cur, col], table) };
    });
  }

  function selectAllColumns(key: string, table: TableInfo, safeOnly: boolean) {
    const cols = table.columns
      .filter((c) => (safeOnly ? !c.sensitive : true))
      .map((c) => c.name);
    setPickedColumns((prev) => ({
      ...prev,
      [key]: ensurePrimaryKey(cols, table),
    }));
  }

  function onPublish(activate: boolean) {
    setError(null);
    if (!slugify(specName)) {
      setError("Spec name is required.");
      return;
    }
    if (draft.endpoints.length === 0) {
      setError("Add at least one endpoint before publishing.");
      return;
    }
    startTransition(async () => {
      try {
        const check = await validateSpec(draft, true);
        if (!check.valid) {
          setError(check.errors.join("; "));
          return;
        }
        const name = slugify(specName);
        await saveSpec(name, draft);
        if (activate) await activateSpec(draft, name);
        setMessage(activate ? `Saved & activated '${name}'.` : `Saved '${name}'.`);
        router.push(`/studio/${encodeURIComponent(name)}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Publish failed");
      }
    });
  }

  return (
    <>
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>Design flow</p>
        <h1 className={styles.title}>New API</h1>
        <p className={styles.lede}>
          Three steps: connect → pick tables &amp; columns → guards &amp; publish.
        </p>
      </section>

      <div className={styles.steps} role="tablist" aria-label="Wizard steps">
        {STEPS.map((label, i) => (
          <button
            key={label}
            type="button"
            role="tab"
            aria-selected={i === step}
            className={i === step ? styles.stepOn : i < step ? styles.stepDone : styles.step}
            onClick={() => goStep(i)}
          >
            {i + 1}. {label}
          </button>
        ))}
      </div>

      {(message || error) && (
        <div className={error ? styles.bannerErr : styles.bannerOk} role={error ? "alert" : "status"}>
          {error ?? message}
        </div>
      )}

      {step === 0 && (
        <section className={styles.panel}>
          <h2>Connect Postgres</h2>
          <p>Studio only introspects what you point at. Nothing is exposed yet.</p>
          <div className={styles.formGrid}>
            <label className={styles.span2}>
              Database URL
              <div className={styles.passwordRow}>
                <input
                  type={showPass ? "text" : "password"}
                  value={dbUrl}
                  onChange={(e) => setDbUrl(e.target.value)}
                  spellCheck={false}
                  autoComplete="off"
                />
                <button type="button" className={styles.ghost} onClick={() => setShowPass((v) => !v)}>
                  {showPass ? "Hide" : "Show"}
                </button>
              </div>
              <span className={styles.hint}>
                Docker Compose: use host <code>db</code> and port <code>5432</code> (e.g.{" "}
                <code>…@db:5432/app</code>). From your laptop outside Docker use{" "}
                <code>localhost:5433</code>.
              </span>
            </label>
            <label>
              Postgres schema (usually public)
              <input value={schema} onChange={(e) => setSchema(e.target.value)} />
              <span className={styles.hint}>
                Schema namespace for tables — not “public API”. Default is <code>public</code>.
              </span>
            </label>
            <label>
              Spec file name
              <input value={specName} onChange={(e) => setSpecName(e.target.value)} />
            </label>
          </div>
          <div className={styles.toolbar}>
            <button type="button" className={styles.primary} onClick={onIntrospect} disabled={pending}>
              Introspect &amp; continue
            </button>
          </div>
        </section>
      )}

      {step === 1 && (
        <section className={styles.panel}>
          <h2>Pick tables &amp; columns</h2>
          <p>
            Expand a table to choose which columns become API fields. Sensitive columns stay off
            unless you enable them later in the editor.
          </p>
          <div className={styles.sourceList}>
            {tables.map((t) => {
              const key = tableKey(t);
              const selected = pickedColumns[key] ?? [];
              const on = selected.length > 0;
              const open = expanded === key;
              return (
                <div key={key} className={styles.sourceCard}>
                  <div className={styles.sourceRow}>
                    <button
                      type="button"
                      className={styles.sourceExpand}
                      aria-expanded={open}
                      onClick={() => setExpanded(open ? null : key)}
                    >
                      <span aria-hidden>{open ? "▾" : "▸"}</span>
                      <strong>
                        {t.schema}.{t.name}
                      </strong>
                      <span className={styles.sourceMeta}>
                        {t.kind ?? "table"} · {selected.length}/{t.columns.length} cols
                      </span>
                    </button>
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => toggleTable(key, t)}
                      aria-label={`Include ${t.schema}.${t.name}`}
                    />
                  </div>
                  {open && (
                    <div className={styles.columnPicker}>
                      <div className={styles.columnToolbar}>
                        <button
                          type="button"
                          className={styles.ghost}
                          onClick={() => selectAllColumns(key, t, true)}
                        >
                          Safe only
                        </button>
                        <button
                          type="button"
                          className={styles.ghost}
                          onClick={() => selectAllColumns(key, t, false)}
                        >
                          Select all
                        </button>
                      </div>
                      <ul className={styles.columnList}>
                        {t.columns.map((c) => {
                          const checked = selected.includes(c.name);
                          const isPk = t.primary_keys.includes(c.name);
                          return (
                            <li key={c.name}>
                              <label
                                className={
                                  c.sensitive ? styles.columnRowSensitive : styles.columnRow
                                }
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  disabled={c.sensitive && !checked}
                                  onChange={() => {
                                    if (c.sensitive && !checked) return;
                                    toggleColumn(key, t, c.name);
                                  }}
                                />
                                <span>
                                  {c.name}
                                  {isPk ? " · pk" : ""}
                                  {c.sensitive ? " · sensitive" : ""}
                                </span>
                                <em>{c.type}</em>
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
            {tables.length === 0 && <p>No tables loaded — go back to Connect.</p>}
          </div>
          <div className={styles.toolbar}>
            <button type="button" className={styles.ghost} onClick={() => setStep(0)}>
              Back
            </button>
            <button
              type="button"
              className={styles.primary}
              disabled={pickedKeys.length === 0}
              onClick={() => goStep(2)}
            >
              Continue
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section className={styles.panel}>
          <h2>Guards &amp; publish</h2>
          <p>Defaults favor read-only + API key. Leave prefix empty for URLs without a version.</p>
          <div className={styles.formGrid}>
            <label>
              API title
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              API prefix
              <input
                value={apiPrefix}
                onChange={(e) => setApiPrefix(e.target.value)}
                placeholder="(empty = no version)"
                spellCheck={false}
              />
              <span className={styles.hint}>Empty = paths like <code>/customers</code>, not <code>/v1/…</code></span>
            </label>
            <label>
              Auth
              <select
                value={auth}
                onChange={(e) => setAuth(e.target.value as ApiSpecDraft["app"]["auth"])}
              >
                <option value="api_key">API key</option>
                <option value="jwt">JWT + RBAC</option>
                <option value="none">None (dev)</option>
              </select>
            </label>
            <label className={styles.checkField}>
              <input
                type="checkbox"
                checked={readOnly}
                onChange={(e) => setReadOnly(e.target.checked)}
              />
              Read-only API
            </label>
          </div>
          <div className={styles.chipRow}>
            {draft.endpoints.map((ep) => (
              <span key={ep.name} className={styles.chipOn}>
                GET {formatApiPath(apiPrefix, ep.path)}
                <span className={styles.sourceMeta}> · {ep.fields.length} fields</span>
              </span>
            ))}
          </div>
          <pre className={styles.review}>
            {`name: ${slugify(specName)}
title: ${title}
prefix: ${apiPrefix || "(none)"}
auth: ${auth}
read_only: ${readOnly}
endpoints: ${draft.endpoints.length}
${draft.endpoints
  .map(
    (e) =>
      `  - GET ${formatApiPath(apiPrefix, e.path)} ← ${e.schema}.${e.table} [${e.fields.join(", ")}]`,
  )
  .join("\n")}`}
          </pre>
          <div className={styles.toolbar}>
            <button type="button" className={styles.ghost} onClick={() => setStep(1)}>
              Back
            </button>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => onPublish(false)}
              disabled={pending}
            >
              Save only
            </button>
            <button
              type="button"
              className={styles.primary}
              onClick={() => onPublish(true)}
              disabled={pending}
            >
              Save &amp; activate
            </button>
          </div>
        </section>
      )}
    </>
  );
}
