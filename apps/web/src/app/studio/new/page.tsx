"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import {
  activateSpec,
  introspectDatabase,
  saveSpec,
  validateSpec,
} from "@/lib/api";
import { tableKey } from "@/lib/tableKey";
import type { ApiSpecDraft, EndpointDraft, TableInfo } from "@/lib/types";
import { ALL_FILTER_OPS } from "@/lib/types";
import styles from "@/components/studio/flow.module.css";

const STEPS = ["Connect", "Sources", "Shape", "Guards", "Review"] as const;

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
  const [dbUrl, setDbUrl] = useState("postgresql://postgres:postgres@localhost:5433/app");
  const [showPass, setShowPass] = useState(false);
  const [schema, setSchema] = useState("public");
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [auth, setAuth] = useState<ApiSpecDraft["app"]["auth"]>("api_key");
  const [readOnly, setReadOnly] = useState(true);
  const [title, setTitle] = useState("My Data API");
  const [apiPrefix, setApiPrefix] = useState("/v1");

  const draft = useMemo((): ApiSpecDraft => {
    const used = new Set<string>();
    const endpoints: EndpointDraft[] = [];
    for (const key of picked) {
      const table = tables.find((t) => tableKey(t) === key);
      if (!table) continue;
      const name = uniqueEndpointName(table.name, used);
      const safe = table.columns.filter((c) => !c.sensitive).map((c) => c.name);
      const pk = table.primary_keys[0] ?? safe[0] ?? "id";
      const fields = safe.includes(pk) ? safe.slice(0, 12) : [pk, ...safe].slice(0, 12);
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
  }, [picked, tables, dbUrl, title, readOnly, auth, apiPrefix]);

  function goStep(i: number) {
    if (i > 0 && tables.length === 0) {
      setError("Connect and introspect the database first.");
      return;
    }
    if (i > 1 && picked.length === 0) {
      setError("Pick at least one table or view.");
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
        setMessage(`Found ${result.count} tables/views.`);
        setStep(1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Introspect failed");
      }
    });
  }

  function togglePick(key: string) {
    setPicked((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]));
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
          Five light steps: connect → pick sources → name the surface → set guards → review.
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
            </label>
            <label>
              Schema
              <input value={schema} onChange={(e) => setSchema(e.target.value)} />
            </label>
            <label>
              Spec file name
              <input value={specName} onChange={(e) => setSpecName(e.target.value)} />
            </label>
          </div>
          <div className={styles.toolbar}>
            <button type="button" className={styles.primary} onClick={onIntrospect} disabled={pending}>
              Introspect & continue
            </button>
          </div>
        </section>
      )}

      {step === 1 && (
        <section className={styles.panel}>
          <h2>Pick sources</h2>
          <p>Tables and views become endpoints. Schema-qualified so duplicates don’t collide.</p>
          <div className={styles.sourceList}>
            {tables.map((t) => {
              const key = tableKey(t);
              return (
                <label key={key} className={styles.sourceRow}>
                  <span>
                    <strong>
                      {t.schema}.{t.name}
                    </strong>
                    <span style={{ color: "var(--ink-soft)", marginLeft: 8 }}>
                      {t.kind ?? "table"} · {t.columns.length} cols
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    checked={picked.includes(key)}
                    onChange={() => togglePick(key)}
                  />
                </label>
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
              disabled={picked.length === 0}
              onClick={() => goStep(2)}
            >
              Continue
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section className={styles.panel}>
          <h2>Shape the API</h2>
          <p>Public title and URL prefix. Endpoint paths default from table names — edit after save.</p>
          <div className={styles.formGrid}>
            <label>
              API title
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              API prefix
              <input value={apiPrefix} onChange={(e) => setApiPrefix(e.target.value)} />
            </label>
          </div>
          <div className={styles.chipRow}>
            {draft.endpoints.map((ep) => (
              <span key={ep.name} className={styles.chipOn}>
                GET {apiPrefix}
                {ep.path}
              </span>
            ))}
          </div>
          <div className={styles.toolbar}>
            <button type="button" className={styles.ghost} onClick={() => setStep(1)}>
              Back
            </button>
            <button type="button" className={styles.primary} onClick={() => goStep(3)}>
              Continue
            </button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className={styles.panel}>
          <h2>Guards</h2>
          <p>Defaults favor read-only + API key. Tighten later with JWT roles and row-level rules.</p>
          <div className={styles.formGrid}>
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
            <label className={styles.field} style={{ alignContent: "end" }}>
              <span style={{ display: "flex", gap: 8, alignItems: "center", textTransform: "none" }}>
                <input
                  type="checkbox"
                  checked={readOnly}
                  onChange={(e) => setReadOnly(e.target.checked)}
                />
                Read-only API
              </span>
            </label>
          </div>
          <div className={styles.toolbar}>
            <button type="button" className={styles.ghost} onClick={() => setStep(2)}>
              Back
            </button>
            <button type="button" className={styles.primary} onClick={() => goStep(4)}>
              Review
            </button>
          </div>
        </section>
      )}

      {step === 4 && (
        <section className={styles.panel}>
          <h2>Review & publish</h2>
          <p>Validate against the live database, save YAML, optionally activate under /data.</p>
          <pre className={styles.review}>
            {`name: ${slugify(specName)}
title: ${title}
prefix: ${apiPrefix}
auth: ${auth}
read_only: ${readOnly}
endpoints: ${draft.endpoints.length}
${draft.endpoints.map((e) => `  - ${e.methods.join(",")} ${apiPrefix}${e.path} ← ${e.schema}.${e.table}`).join("\n")}`}
          </pre>
          <div className={styles.toolbar}>
            <button type="button" className={styles.ghost} onClick={() => setStep(3)}>
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
              Save & activate
            </button>
          </div>
        </section>
      )}
    </>
  );
}
