"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import {
  activateSpec,
  buildClientSnippet,
  buildYaml,
  dumpYaml,
  getApiBase,
  getDataApiKey,
  introspectDatabase,
  issueToken,
  listSpecs,
  loadSpec,
  previewSql,
  saveSpec,
  tryDataRequest,
  validateSpec,
} from "@/lib/api";
import { copyText } from "@/lib/copy";
import { tableKey } from "@/lib/tableKey";
import type {
  ApiSpecDraft,
  EndpointDraft,
  RelationDraft,
  TableInfo,
  ValidateResult,
} from "@/lib/types";
import { ALL_FILTER_OPS, ALL_METHODS } from "@/lib/types";
import styles from "./studio.module.css";

const emptySpec = (url: string): ApiSpecDraft => ({
  database: { url },
  app: {
    title: "My Data API",
    version: "0.3.0",
    description: "Spec-first API over Postgres",
    read_only: true,
    auth: "api_key",
    api_prefix: "/v1",
    cache: { enabled: true, ttl_seconds: 30 },
    idempotency: { enabled: true, required_for_writes: false, ttl_seconds: 86400 },
    rate_limit: { enabled: true, requests_per_minute: 120 },
    audit_enabled: true,
    compression: true,
    tracing: true,
    rbac: [],
  },
  endpoints: [],
});

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "resource";
}

type EditorTab = "contract" | "security" | "relations" | "sql" | "play" | "yaml";

export function StudioShell({
  initialName,
  embedded = false,
}: {
  initialName?: string;
  embedded?: boolean;
}) {
  const [dbUrl, setDbUrl] = useState("postgresql://postgres:postgres@localhost:5433/app");
  const [schema, setSchema] = useState("public");
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [spec, setSpec] = useState<ApiSpecDraft>(() => emptySpec(dbUrl));
  const [activeEndpoint, setActiveEndpoint] = useState<string | null>(null);
  const [specName, setSpecName] = useState(initialName ?? "demo");
  const [savedNames, setSavedNames] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [editorTab, setEditorTab] = useState<EditorTab>("contract");
  const [yamlText, setYamlText] = useState("");
  const [pending, startTransition] = useTransition();
  const [dirty, setDirty] = useState(false);
  const [showDbUrl, setShowDbUrl] = useState(false);
  const yamlWarnOnce = useRef(false);
  const skipDirty = useRef(true);

  // Playground
  const [playMethod, setPlayMethod] = useState("GET");
  const [playPath, setPlayPath] = useState("/v1/customers");
  const [playQuery, setPlayQuery] = useState("limit=5");
  const [playBody, setPlayBody] = useState("");
  const [playBearer, setPlayBearer] = useState("");
  const [playRoles, setPlayRoles] = useState("analyst");
  const [playExpiresMin, setPlayExpiresMin] = useState(15);
  const [playResult, setPlayResult] = useState<string>("");
  const [sqlDraft, setSqlDraft] = useState(
    "SELECT id, name, email, created_at\nFROM customers\nWHERE deleted_at IS NULL",
  );

  const selected = tables.find((t) => tableKey(t) === selectedTable) ?? null;
  const endpoint = spec.endpoints.find((e) => e.name === activeEndpoint) ?? null;
  const draftSpec = useMemo(
    () => ({ ...spec, database: { url: dbUrl } }),
    [spec, dbUrl],
  );
  const localYaml = useMemo(() => buildYaml(draftSpec), [draftSpec]);
  const snippets = useMemo(
    () =>
      buildClientSnippet({
        base: getApiBase(),
        path: playPath,
        method: playMethod,
        authMode: spec.app.auth,
        query: playQuery,
      }),
    [playPath, playMethod, playQuery, spec.app.auth],
  );

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void dumpYaml(draftSpec)
        .then((text) => {
          if (!cancelled) setYamlText(text);
        })
        .catch(() => {
          if (cancelled) return;
          setYamlText(localYaml);
          if (!yamlWarnOnce.current) {
            yamlWarnOnce.current = true;
            setMessage("Server YAML dump unavailable; showing local fallback (may be incomplete).");
          }
        });
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [draftSpec, localYaml]);

  useEffect(() => {
    if (skipDirty.current) {
      skipDirty.current = false;
      return;
    }
    setDirty(true);
  }, [draftSpec]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!endpoint) return;
    const prefix = spec.app.api_prefix || "";
    setPlayPath(`${prefix}${endpoint.path}`);
  }, [endpoint?.path, endpoint?.name, spec.app.api_prefix]);

  useEffect(() => {
    if (!initialName) return;
    startTransition(async () => {
      try {
        const loaded = await loadSpec(initialName);
        skipDirty.current = true;
        setSpec(loaded.spec);
        setDbUrl(loaded.spec.database.url);
        setSpecName(initialName);
        setActiveEndpoint(loaded.spec.endpoints[0]?.name ?? null);
        setDirty(false);
        setMessage(`Loaded '${initialName}'.`);
        const schemaHint = loaded.spec.endpoints[0]?.schema || "public";
        try {
          const intro = await introspectDatabase(loaded.spec.database.url, schemaHint);
          setTables(intro.tables);
          setSchema(schemaHint);
        } catch (e) {
          setMessage(
            `Loaded '${initialName}' (introspect warning: ${
              e instanceof Error ? e.message : "failed"
            }).`,
          );
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Load failed");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialName]);

  function setStatus(ok: string | null, err: string | null = null) {
    setMessage(ok);
    setError(err);
  }

  async function onCopy(text: string, label: string) {
    const ok = await copyText(text);
    setStatus(ok ? `Copied ${label}.` : `Could not copy ${label}.`);
  }

  function patchApp(patch: Partial<ApiSpecDraft["app"]>) {
    setSpec((prev) => ({ ...prev, app: { ...prev.app, ...patch } }));
  }

  function updateEndpoint(patch: Partial<EndpointDraft>) {
    if (!endpoint) return;
    const oldName = endpoint.name;
    const renamed =
      patch.name !== undefined
        ? patch.name.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_|_$/g, "") ||
          oldName
        : oldName;
    if (renamed !== oldName && spec.endpoints.some((e) => e.name === renamed)) {
      setStatus(null, `Endpoint name '${renamed}' already exists.`);
      return;
    }
    setSpec((prev) => ({
      ...prev,
      endpoints: prev.endpoints.map((e) => {
        if (e.name !== oldName) return e;
        return { ...e, ...patch, name: renamed };
      }),
    }));
    if (renamed !== oldName) setActiveEndpoint(renamed);
  }

  function removeEndpoint() {
    if (!endpoint) return;
    if (!window.confirm(`Remove endpoint '${endpoint.name}'?`)) return;
    setSpec((prev) => ({
      ...prev,
      endpoints: prev.endpoints.filter((e) => e.name !== endpoint.name),
    }));
    setActiveEndpoint(null);
  }

  function onIntrospect() {
    setStatus(null);
    startTransition(async () => {
      try {
        const result = await introspectDatabase(dbUrl, schema);
        setTables(result.tables);
        setSpec((prev) => ({ ...prev, database: { url: dbUrl } }));
        setStatus(`Loaded ${result.count} tables/views from schema '${schema}'.`);
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Introspection failed");
      }
    });
  }

  function addEndpointFromTable(table: TableInfo) {
    let name = slugify(table.name);
    let i = 2;
    while (spec.endpoints.some((e) => e.name === name)) {
      name = `${slugify(table.name)}_${i++}`;
    }
    const safeFields = table.columns.filter((c) => !c.sensitive).map((c) => c.name);
    const pk = table.primary_keys[0] ?? safeFields[0] ?? "id";
    const fields = safeFields.includes(pk) ? safeFields : [pk, ...safeFields];
    const draft: EndpointDraft = {
      name,
      path: `/${name}`,
      table: table.name,
      schema: table.schema,
      methods: ["GET"],
      primary_key: pk,
      fields: fields.slice(0, 12),
      writable_fields: fields.filter((f) => f !== pk).slice(0, 8),
      filters: fields.filter((f) => f !== pk).slice(0, 3),
      filter_operators: [...ALL_FILTER_OPS],
      sortable: [pk, ...(fields.includes("created_at") ? ["created_at"] : [])],
      pagination: { enabled: true, mode: "cursor", default_limit: 20, max_limit: 100 },
      relations: [],
      roles: [],
      validations: [],
      bulk_enabled: true,
      async_writes: false,
      csv_export: true,
      description: `API for ${table.kind === "view" ? "view" : "table"} ${table.name}`,
    };
    setSpec((prev) => ({
      ...prev,
      endpoints: [...prev.endpoints, draft],
      app: {
        ...prev.app,
        read_only: prev.app.read_only && !draft.methods.some((m) => m !== "GET"),
      },
    }));
    setActiveEndpoint(name);
    setSelectedTable(tableKey(table));
    setEditorTab("contract");
    setStatus(`Added endpoint ${draft.path} (name=${name}). Rename freely.`);
  }

  function addSqlEndpoint() {
    let name = "custom_query";
    let i = 2;
    while (spec.endpoints.some((e) => e.name === name)) name = `custom_query_${i++}`;
    const draft: EndpointDraft = {
      name,
      path: `/analytics/${name}`,
      table: "_sql",
      schema: "public",
      sql: sqlDraft,
      methods: ["GET"],
      primary_key: "id",
      fields: ["id"],
      filters: [],
      filter_operators: [...ALL_FILTER_OPS],
      sortable: ["id"],
      pagination: { enabled: true, mode: "offset", default_limit: 50, max_limit: 200 },
      csv_export: true,
      description: "Custom SQL / metrics endpoint",
    };
    setSpec((prev) => ({ ...prev, endpoints: [...prev.endpoints, draft] }));
    setActiveEndpoint(name);
    setEditorTab("sql");
    setStatus("Added SQL endpoint — run Discover columns, then Activate.");
  }

  function toggleField(field: string, list: "fields" | "filters" | "sortable" | "writable_fields") {
    if (!endpoint) return;
    const current = new Set(endpoint[list] ?? []);
    if (current.has(field)) {
      if (list === "fields" && field === endpoint.primary_key) return;
      current.delete(field);
    } else {
      current.add(field);
    }
    const next = [...current];
    if (list === "fields") {
      updateEndpoint({
        fields: next,
        filters: endpoint.filters.filter((f) => next.includes(f)),
        sortable: endpoint.sortable.filter((f) => next.includes(f)),
        writable_fields: (endpoint.writable_fields ?? []).filter((f) => next.includes(f)),
      });
      return;
    }
    updateEndpoint({ [list]: next } as Partial<EndpointDraft>);
  }

  function toggleMethod(method: string) {
    if (!endpoint || endpoint.sql) return;
    const set = new Set(endpoint.methods);
    if (set.has(method)) {
      if (method === "GET") return;
      set.delete(method);
    } else {
      set.add(method);
      if (method !== "GET") patchApp({ read_only: false });
    }
    updateEndpoint({ methods: [...set] });
  }

  function addRelation(child: TableInfo) {
    if (!endpoint || !selected) return;
    const fk = child.foreign_keys.find((f) => f.ref_table === selected.name);
    if (!fk) {
      setStatus(null, `${child.name} does not reference ${selected.name}`);
      return;
    }
    const relName = slugify(child.name);
    if (endpoint.relations?.some((r) => r.name === relName)) {
      setStatus(null, `Relation '${relName}' already exists.`);
      return;
    }
    const safeFields = child.columns.filter((c) => !c.sensitive).map((c) => c.name);
    const rel: RelationDraft = {
      name: relName,
      table: child.name,
      schema: child.schema,
      type: "one_to_many",
      local_key: fk.ref_column || endpoint.primary_key,
      foreign_key: fk.column,
      fields: safeFields.slice(0, 8),
      primary_key: child.primary_keys[0] ?? "id",
      max_per_parent: 50,
    };
    updateEndpoint({ relations: [...(endpoint.relations ?? []), rel] });
    setStatus(`Added relation ${relName}`);
  }

  function removeRelation(name: string) {
    if (!endpoint) return;
    updateEndpoint({
      relations: (endpoint.relations ?? []).filter((r) => r.name !== name),
    });
  }

  function onValidate() {
    setStatus(null);
    startTransition(async () => {
      try {
        const result = await validateSpec(draftSpec, true);
        setValidation(result);
        setStatus(result.valid ? "Specification is valid." : "Specification has errors.");
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Validate failed");
      }
    });
  }

  function onActivate() {
    setStatus(null);
    if (draftSpec.endpoints.length === 0) {
      setStatus(null, "Add at least one endpoint before activating.");
      return;
    }
    startTransition(async () => {
      try {
        const result = await activateSpec(draftSpec, specName);
        setStatus(`${result.message} → ${getApiBase()}${result.docs_path}`);
        if (endpoint) {
          const prefix = draftSpec.app.api_prefix || "";
          setPlayPath(`${prefix}${endpoint.path}`);
          setPlayMethod("GET");
          setEditorTab("play");
        }
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Activate failed");
      }
    });
  }

  function onSave() {
    setStatus(null);
    startTransition(async () => {
      try {
        await saveSpec(specName, draftSpec);
        const listed = await listSpecs();
        setSavedNames(listed.specs.map((s) => s.name));
        setDirty(false);
        setStatus(`Saved spec '${specName}'.`);
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Save failed");
      }
    });
  }

  function onLoad(name: string) {
    setStatus(null);
    startTransition(async () => {
      try {
        const loaded = await loadSpec(name);
        skipDirty.current = true;
        setSpec(loaded.spec);
        setDbUrl(loaded.spec.database.url);
        setSpecName(name);
        setActiveEndpoint(loaded.spec.endpoints[0]?.name ?? null);
        setDirty(false);
        setStatus(`Loaded spec '${name}'.`);
        const schemaHint = loaded.spec.endpoints[0]?.schema || "public";
        try {
          const intro = await introspectDatabase(loaded.spec.database.url, schemaHint);
          setTables(intro.tables);
          setSchema(schemaHint);
        } catch (e) {
          setMessage(
            `Loaded spec '${name}' (introspect warning: ${
              e instanceof Error ? e.message : "failed"
            }).`,
          );
        }
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Load failed");
      }
    });
  }

  function refreshSaved() {
    startTransition(async () => {
      try {
        const listed = await listSpecs();
        setSavedNames(listed.specs.map((s) => s.name));
      } catch {
        /* ignore */
      }
    });
  }

  function onDiscoverSql() {
    if (!endpoint) return;
    const sql = endpoint.sql || sqlDraft;
    startTransition(async () => {
      try {
        const result = await previewSql(dbUrl, sql);
        const fields = result.columns;
        const pk = fields.includes("id") ? "id" : fields[0];
        updateEndpoint({
          sql,
          fields,
          primary_key: pk,
          sortable: [pk],
          filters: fields.filter((f) => f !== pk).slice(0, 5),
        });
        setStatus(`Discovered ${fields.length} columns from SQL.`);
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "SQL preview failed");
      }
    });
  }

  function onRefreshYaml() {
    startTransition(async () => {
      try {
        const text = await dumpYaml(draftSpec);
        setYamlText(text);
        setStatus("YAML refreshed from server dump.");
      } catch {
        setYamlText(localYaml);
        setStatus(
          "Server YAML dump failed; local fallback YAML is incomplete.",
        );
      }
    });
  }

  function onTry() {
    if (["POST", "PATCH", "PUT"].includes(playMethod)) {
      try {
        JSON.parse(playBody);
      } catch {
        setPlayResult("Request body is not valid JSON. Fix the body before sending.");
        return;
      }
    }
    startTransition(async () => {
      try {
        let bearer = playBearer;
        if (spec.app.auth === "jwt" && !bearer) {
          const roles = playRoles
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
          const tok = await issueToken(
            roles.length ? roles : ["analyst"],
            "studio-user",
            Number.isFinite(playExpiresMin) ? playExpiresMin : 15,
          );
          bearer = tok.access_token;
          setPlayBearer(bearer);
        }
        const result = await tryDataRequest({
          method: playMethod,
          path: playPath,
          query: playQuery,
          body: playBody,
          authMode: spec.app.auth,
          bearer,
        });
        const headerLines = Object.entries(result.headers)
          .filter(([k]) =>
            ["etag", "link", "x-ratelimit-limit", "x-ratelimit-remaining", "x-trace-id", "content-type"].includes(
              k.toLowerCase(),
            ),
          )
          .map(([k, v]) => `${k}: ${v}`)
          .join("\n");
        setPlayResult(
          `HTTP ${result.status} (${result.ms}ms)\n${headerLines}\n\n${result.body.slice(0, 8000)}`,
        );
      } catch (e) {
        setPlayResult(e instanceof Error ? e.message : "Request failed");
      }
    });
  }

  const childTables = selected
    ? tables.filter((t) => t.foreign_keys.some((fk) => fk.ref_table === selected.name))
    : [];

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
        </div>
      )}

      <section className={styles.connectWide}>
        <label>
          Postgres URL
          <div className={styles.inputWithBtn}>
            <input
              type={showDbUrl ? "text" : "password"}
              value={dbUrl}
              onChange={(e) => setDbUrl(e.target.value)}
              spellCheck={false}
              autoComplete="off"
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
          Schema
          <input value={schema} onChange={(e) => setSchema(e.target.value)} />
        </label>
        <label>
          Spec name
          <input value={specName} onChange={(e) => setSpecName(e.target.value)} />
        </label>
        <label>
          Auth
          <select
            value={spec.app.auth}
            onChange={(e) => patchApp({ auth: e.target.value as ApiSpecDraft["app"]["auth"] })}
          >
            <option value="api_key">API key</option>
            <option value="jwt">JWT + RBAC</option>
            <option value="none">None (dev)</option>
          </select>
        </label>
        <label>
          API prefix
          <input
            value={spec.app.api_prefix ?? "/v1"}
            onChange={(e) => patchApp({ api_prefix: e.target.value })}
          />
        </label>
        <div className={styles.rowGap}>
          <button type="button" className={styles.primary} onClick={onIntrospect} disabled={pending}>
            Introspect
          </button>
          <button type="button" className={styles.secondary} onClick={onSave} disabled={pending}>
            Save
          </button>
          <button type="button" className={styles.secondary} onClick={refreshSaved}>
            List
          </button>
        </div>
      </section>

      <section className={styles.connectWide}>
        <label>
          Title
          <input value={spec.app.title} onChange={(e) => patchApp({ title: e.target.value })} />
        </label>
        <label>
          Version
          <input value={spec.app.version} onChange={(e) => patchApp({ version: e.target.value })} />
        </label>
        <label className={styles.span2}>
          Description
          <input
            value={spec.app.description}
            onChange={(e) => patchApp({ description: e.target.value })}
          />
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={spec.app.read_only}
            onChange={(e) => patchApp({ read_only: e.target.checked })}
          />
          Read-only API
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={spec.app.cache?.enabled ?? true}
            onChange={(e) =>
              patchApp({
                cache: {
                  enabled: e.target.checked,
                  ttl_seconds: spec.app.cache?.ttl_seconds ?? 30,
                },
              })
            }
          />
          Cache
        </label>
        <label>
          Cache TTL (s)
          <input
            type="number"
            min={0}
            value={spec.app.cache?.ttl_seconds ?? 30}
            onChange={(e) =>
              patchApp({
                cache: {
                  enabled: spec.app.cache?.enabled ?? true,
                  ttl_seconds: Number(e.target.value) || 0,
                },
              })
            }
          />
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={spec.app.rate_limit.enabled}
            onChange={(e) =>
              patchApp({
                rate_limit: {
                  ...spec.app.rate_limit,
                  enabled: e.target.checked,
                },
              })
            }
          />
          Rate limit
        </label>
        <label>
          Rate / min
          <input
            type="number"
            min={1}
            value={spec.app.rate_limit.requests_per_minute}
            onChange={(e) =>
              patchApp({
                rate_limit: {
                  ...spec.app.rate_limit,
                  requests_per_minute: Number(e.target.value) || 1,
                },
              })
            }
          />
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={spec.app.idempotency?.enabled ?? true}
            onChange={(e) =>
              patchApp({
                idempotency: {
                  enabled: e.target.checked,
                  required_for_writes: spec.app.idempotency?.required_for_writes ?? false,
                  ttl_seconds: spec.app.idempotency?.ttl_seconds ?? 86400,
                },
              })
            }
          />
          Idempotency
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={spec.app.idempotency?.required_for_writes ?? false}
            onChange={(e) =>
              patchApp({
                idempotency: {
                  enabled: spec.app.idempotency?.enabled ?? true,
                  required_for_writes: e.target.checked,
                  ttl_seconds: spec.app.idempotency?.ttl_seconds ?? 86400,
                },
              })
            }
          />
          Idempotency required for writes
        </label>
        <label>
          Idempotency TTL (s)
          <input
            type="number"
            min={0}
            value={spec.app.idempotency?.ttl_seconds ?? 86400}
            onChange={(e) =>
              patchApp({
                idempotency: {
                  enabled: spec.app.idempotency?.enabled ?? true,
                  required_for_writes: spec.app.idempotency?.required_for_writes ?? false,
                  ttl_seconds: Number(e.target.value) || 0,
                },
              })
            }
          />
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={spec.app.compression ?? true}
            onChange={(e) => patchApp({ compression: e.target.checked })}
          />
          Gzip
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={spec.app.audit_enabled ?? true}
            onChange={(e) => patchApp({ audit_enabled: e.target.checked })}
          />
          Audit
        </label>
      </section>

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

      <div className={styles.grid}>
        <aside className={styles.panel}>
          <div className={styles.panelHead}>
            <h2>Schema</h2>
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
            {tables.length === 0 && <li className={styles.empty}>Introspect to load tables/views.</li>}
          </ul>
          <div className={styles.stackBtns}>
            {selected && (
              <button
                type="button"
                className={styles.secondary}
                onClick={() => addEndpointFromTable(selected)}
              >
                Add endpoint from {selected.kind === "view" ? "view" : "table"}
              </button>
            )}
            <button type="button" className={styles.secondary} onClick={addSqlEndpoint}>
              Add SQL / metrics endpoint
            </button>
          </div>
        </aside>

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

              {editorTab === "contract" && (
                <div className={styles.editorBlock}>
                  <div className={styles.metaGrid}>
                    <label>
                      Name (id)
                      <input
                        value={endpoint.name}
                        onChange={(e) => updateEndpoint({ name: e.target.value })}
                        spellCheck={false}
                      />
                    </label>
                    <label>
                      Path (URL)
                      <input
                        value={endpoint.path}
                        onChange={(e) => updateEndpoint({ path: e.target.value })}
                        spellCheck={false}
                      />
                    </label>
                    <label>
                      Primary key
                      <select
                        value={endpoint.primary_key}
                        onChange={(e) => updateEndpoint({ primary_key: e.target.value })}
                      >
                        {endpoint.fields.map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Pagination mode
                      <select
                        value={endpoint.pagination?.mode ?? "cursor"}
                        onChange={(e) =>
                          updateEndpoint({
                            pagination: {
                              enabled: endpoint.pagination?.enabled ?? true,
                              mode: e.target.value as "cursor" | "offset",
                              default_limit: endpoint.pagination?.default_limit ?? 20,
                              max_limit: endpoint.pagination?.max_limit ?? 100,
                            },
                          })
                        }
                      >
                        <option value="cursor">Cursor</option>
                        <option value="offset">Offset</option>
                      </select>
                    </label>
                    <label>
                      Default limit
                      <input
                        type="number"
                        min={1}
                        value={endpoint.pagination?.default_limit ?? 20}
                        onChange={(e) =>
                          updateEndpoint({
                            pagination: {
                              enabled: endpoint.pagination?.enabled ?? true,
                              mode: endpoint.pagination?.mode ?? "cursor",
                              default_limit: Number(e.target.value) || 1,
                              max_limit: endpoint.pagination?.max_limit ?? 100,
                            },
                          })
                        }
                      />
                    </label>
                    <label>
                      Max limit
                      <input
                        type="number"
                        min={1}
                        value={endpoint.pagination?.max_limit ?? 100}
                        onChange={(e) =>
                          updateEndpoint({
                            pagination: {
                              enabled: endpoint.pagination?.enabled ?? true,
                              mode: endpoint.pagination?.mode ?? "cursor",
                              default_limit: endpoint.pagination?.default_limit ?? 20,
                              max_limit: Number(e.target.value) || 1,
                            },
                          })
                        }
                      />
                    </label>
                    <label className={styles.span2}>
                      Description
                      <input
                        value={endpoint.description ?? ""}
                        onChange={(e) => updateEndpoint({ description: e.target.value })}
                      />
                    </label>
                  </div>
                  <label className={styles.check}>
                    <input
                      type="checkbox"
                      checked={endpoint.pagination?.enabled ?? true}
                      onChange={(e) =>
                        updateEndpoint({
                          pagination: {
                            enabled: e.target.checked,
                            mode: endpoint.pagination?.mode ?? "cursor",
                            default_limit: endpoint.pagination?.default_limit ?? 20,
                            max_limit: endpoint.pagination?.max_limit ?? 100,
                          },
                        })
                      }
                    />
                    Pagination enabled
                  </label>
                  <label className={styles.check}>
                    <input
                      type="checkbox"
                      checked={endpoint.allow_sensitive ?? false}
                      onChange={(e) => updateEndpoint({ allow_sensitive: e.target.checked })}
                    />
                    Allow sensitive columns
                  </label>

                  {!endpoint.sql && (
                    <>
                      <h3>Methods</h3>
                      <div className={styles.allowlist}>
                        {ALL_METHODS.map((m) => (
                          <button
                            key={m}
                            type="button"
                            className={[
                              styles.chip,
                              endpoint.methods.includes(m) ? styles.chipOn : "",
                            ].join(" ")}
                            onClick={() => toggleMethod(m)}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </>
                  )}

                  <h3>Fields</h3>
                  <div className={styles.allowlist}>
                    {(selected?.columns ?? endpoint.fields.map((name) => ({ name, sensitive: false, primary_key: name === endpoint.primary_key, type: "", nullable: true }))).map(
                      (col) => {
                        const name = typeof col === "string" ? col : col.name;
                        const on = endpoint.fields.includes(name);
                        const sensitive = typeof col === "object" && col.sensitive;
                        return (
                          <button
                            key={name}
                            type="button"
                            className={[
                              styles.chip,
                              on ? styles.chipOn : "",
                              sensitive ? styles.chipWarn : "",
                            ].join(" ")}
                            onClick={() => toggleField(name, "fields")}
                          >
                            {name}
                          </button>
                        );
                      },
                    )}
                  </div>

                  <div className={styles.twoCol}>
                    <div>
                      <h3>Filters</h3>
                      <div className={styles.allowlist}>
                        {endpoint.fields.map((f) => (
                          <button
                            key={f}
                            type="button"
                            className={[
                              styles.chip,
                              endpoint.filters.includes(f) ? styles.chipOn : "",
                            ].join(" ")}
                            onClick={() => toggleField(f, "filters")}
                          >
                            {f}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h3>Sortable</h3>
                      <div className={styles.allowlist}>
                        {endpoint.fields.map((f) => (
                          <button
                            key={f}
                            type="button"
                            className={[
                              styles.chip,
                              endpoint.sortable.includes(f) ? styles.chipOn : "",
                            ].join(" ")}
                            onClick={() => toggleField(f, "sortable")}
                          >
                            {f}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {!endpoint.sql && (
                    <div>
                      <h3>Writable fields</h3>
                      <div className={styles.allowlist}>
                        {endpoint.fields
                          .filter((f) => f !== endpoint.primary_key)
                          .map((f) => (
                            <button
                              key={f}
                              type="button"
                              className={[
                                styles.chip,
                                (endpoint.writable_fields ?? []).includes(f) ? styles.chipOn : "",
                              ].join(" ")}
                              onClick={() => toggleField(f, "writable_fields")}
                            >
                              {f}
                            </button>
                          ))}
                      </div>
                    </div>
                  )}

                  <h3>Filter operators</h3>
                  <div className={styles.allowlist}>
                    {ALL_FILTER_OPS.map((op) => {
                      const on = (endpoint.filter_operators ?? [...ALL_FILTER_OPS]).includes(op);
                      return (
                        <button
                          key={op}
                          type="button"
                          className={[styles.chip, on ? styles.chipOn : ""].join(" ")}
                          onClick={() => {
                            const cur = new Set(endpoint.filter_operators ?? [...ALL_FILTER_OPS]);
                            if (cur.has(op)) cur.delete(op);
                            else cur.add(op);
                            updateEndpoint({ filter_operators: [...cur] });
                          }}
                        >
                          {op}
                        </button>
                      );
                    })}
                  </div>

                  <div className={styles.rowGap}>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.bulk_enabled ?? true}
                        disabled={!!endpoint.sql}
                        onChange={(e) => updateEndpoint({ bulk_enabled: e.target.checked })}
                      />
                      Bulk POST
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.async_writes ?? false}
                        disabled={!!endpoint.sql}
                        onChange={(e) => updateEndpoint({ async_writes: e.target.checked })}
                      />
                      Async 202 writes
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.csv_export ?? true}
                        onChange={(e) => updateEndpoint({ csv_export: e.target.checked })}
                      />
                      CSV export
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.ndjson_export ?? false}
                        onChange={(e) => updateEndpoint({ ndjson_export: e.target.checked })}
                      />
                      NDJSON export
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.parquet_export ?? false}
                        onChange={(e) => updateEndpoint({ parquet_export: e.target.checked })}
                      />
                      Parquet export
                    </label>
                  </div>
                </div>
              )}

              {editorTab === "security" && (
                <div className={styles.editorBlock}>
                  <label>
                    Required roles (comma-separated)
                    <input
                      value={(endpoint.roles ?? []).join(", ")}
                      onChange={(e) =>
                        updateEndpoint({
                          roles: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        })
                      }
                      placeholder="analyst, admin"
                    />
                  </label>
                  <label>
                    ETag field
                    <select
                      value={endpoint.etag_field ?? ""}
                      onChange={(e) =>
                        updateEndpoint({ etag_field: e.target.value || null })
                      }
                    >
                      <option value="">(hash body)</option>
                      {endpoint.fields.map((f) => (
                        <option key={f} value={f}>
                          {f}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className={styles.twoCol}>
                    <label>
                      Soft-delete column
                      <input
                        value={endpoint.soft_delete?.column ?? ""}
                        disabled={!!endpoint.sql}
                        onChange={(e) =>
                          updateEndpoint({
                            soft_delete: e.target.value
                              ? { column: e.target.value }
                              : null,
                          })
                        }
                        placeholder="deleted_at"
                      />
                    </label>
                    <label>
                      Row-level column
                      <input
                        value={endpoint.row_level?.column ?? ""}
                        disabled={!!endpoint.sql}
                        onChange={(e) =>
                          updateEndpoint({
                            row_level: e.target.value
                              ? {
                                  column: e.target.value,
                                  claim: endpoint.row_level?.claim ?? "sub",
                                  required: endpoint.row_level?.required ?? true,
                                }
                              : null,
                          })
                        }
                        placeholder="owner_id"
                      />
                    </label>
                  </div>
                  {endpoint.row_level && (
                    <label>
                      JWT claim for row-level
                      <input
                        value={endpoint.row_level.claim}
                        onChange={(e) =>
                          updateEndpoint({
                            row_level: { ...endpoint.row_level!, claim: e.target.value },
                          })
                        }
                      />
                    </label>
                  )}
                  <label>
                    Validation (email field, optional)
                    <input
                      value={
                        endpoint.validations?.find((v) => v.format === "email")?.field ?? ""
                      }
                      onChange={(e) => {
                        const field = e.target.value.trim();
                        const rest = (endpoint.validations ?? []).filter(
                          (v) => v.format !== "email",
                        );
                        updateEndpoint({
                          validations: field
                            ? [...rest, { field, format: "email", min_length: 5 }]
                            : rest,
                        });
                      }}
                      placeholder="email"
                    />
                  </label>
                  <div className={styles.twoCol}>
                    <label>
                      Deprecation sunset (YYYY-MM-DD)
                      <input
                        value={endpoint.deprecation?.sunset ?? ""}
                        onChange={(e) =>
                          updateEndpoint({
                            deprecation: {
                              deprecated: Boolean(e.target.value),
                              sunset: e.target.value || null,
                              successor: endpoint.deprecation?.successor ?? null,
                            },
                          })
                        }
                      />
                    </label>
                    <label>
                      Successor path
                      <input
                        value={endpoint.deprecation?.successor ?? ""}
                        onChange={(e) =>
                          updateEndpoint({
                            deprecation: {
                              deprecated: true,
                              sunset: endpoint.deprecation?.sunset ?? null,
                              successor: e.target.value || null,
                            },
                          })
                        }
                      />
                    </label>
                  </div>
                  <label>
                    IP allowlist (comma-separated IPs / prefixes)
                    <input
                      value={(spec.app.ip_allowlist ?? []).join(", ")}
                      onChange={(e) =>
                        patchApp({
                          ip_allowlist: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        })
                      }
                      placeholder="127.0.0.1, 10.0.0."
                    />
                  </label>
                  <label>
                    Webhook URL (optional, fires on writes)
                    <input
                      value={spec.app.webhooks?.[0]?.url ?? ""}
                      onChange={(e) => {
                        const url = e.target.value.trim();
                        if (!url) {
                          patchApp({ webhooks: [] });
                          return;
                        }
                        patchApp({
                          webhooks: [
                            {
                              url,
                              events: ["create", "update", "delete"],
                              secret: spec.app.webhooks?.[0]?.secret ?? "",
                              timeout_seconds: 3,
                            },
                          ],
                        });
                      }}
                      placeholder="https://webhook.site/..."
                    />
                  </label>
                  <label>
                    Webhook HMAC secret
                    <input
                      value={spec.app.webhooks?.[0]?.secret ?? ""}
                      onChange={(e) => {
                        const hooks = spec.app.webhooks ?? [];
                        if (!hooks[0]) return;
                        patchApp({
                          webhooks: [{ ...hooks[0], secret: e.target.value }],
                        });
                      }}
                    />
                  </label>
                  <p className={styles.hint}>
                    App-level RBAC field matrix lives in YAML (`app.rbac`). Data key for try-it:{" "}
                    <code>{getDataApiKey()}</code>
                  </p>
                </div>
              )}

              {editorTab === "relations" && (
                <div className={styles.editorBlock}>
                  {endpoint.sql ? (
                    <p className={styles.empty}>SQL endpoints cannot nest relations.</p>
                  ) : (
                    <>
                      <p className={styles.hint}>
                        Child tables referencing <strong>{selected?.name ?? endpoint.table}</strong> via FK:
                      </p>
                      <div className={styles.rowGap}>
                        {childTables.map((c) => (
                          <button
                            key={c.name}
                            type="button"
                            className={styles.secondary}
                            onClick={() => addRelation(c)}
                          >
                            + {c.name}
                          </button>
                        ))}
                        {childTables.length === 0 && (
                          <span className={styles.empty}>No FK children found.</span>
                        )}
                      </div>
                      <ul className={styles.relList}>
                        {(endpoint.relations ?? []).map((r) => (
                          <li key={r.name}>
                            <code>
                              {r.name}: {r.table}.{r.foreign_key} → {r.local_key}
                            </code>
                            <button
                              type="button"
                              className={styles.dangerBtn}
                              aria-label={`Remove relation ${r.name}`}
                              onClick={() => removeRelation(r.name)}
                            >
                              ×
                            </button>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}

              {editorTab === "sql" && (
                <div className={styles.editorBlock}>
                  <p className={styles.hint}>
                    Read-only SELECT/WITH for metrics &amp; joins. Writes and relations are disabled.
                  </p>
                  <textarea
                    className={styles.sqlBox}
                    value={endpoint.sql ?? sqlDraft}
                    onChange={(e) => {
                      setSqlDraft(e.target.value);
                      updateEndpoint({ sql: e.target.value });
                    }}
                    rows={10}
                    spellCheck={false}
                  />
                  <div className={styles.rowGap}>
                    <button type="button" className={styles.primary} onClick={onDiscoverSql} disabled={pending}>
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
              )}

              {editorTab === "play" && (
                <div className={styles.editorBlock}>
                  <div className={styles.metaGrid}>
                    <label>
                      Method
                      <select value={playMethod} onChange={(e) => setPlayMethod(e.target.value)}>
                        {ALL_METHODS.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className={styles.span2}>
                      Path under /data
                      <input value={playPath} onChange={(e) => setPlayPath(e.target.value)} />
                    </label>
                    <label className={styles.span2}>
                      Query string
                      <input
                        value={playQuery}
                        onChange={(e) => setPlayQuery(e.target.value)}
                        placeholder="limit=5&fields=id,name"
                      />
                    </label>
                    {(playMethod === "POST" || playMethod === "PATCH" || playMethod === "PUT") && (
                      <label className={styles.span2}>
                        JSON body
                        <textarea
                          className={styles.sqlBox}
                          rows={4}
                          value={playBody}
                          onChange={(e) => setPlayBody(e.target.value)}
                        />
                      </label>
                    )}
                    {spec.app.auth === "jwt" && (
                      <>
                        <label className={styles.span2}>
                          Bearer token
                          <input value={playBearer} onChange={(e) => setPlayBearer(e.target.value)} />
                        </label>
                        <label>
                          JWT roles
                          <input
                            value={playRoles}
                            onChange={(e) => setPlayRoles(e.target.value)}
                            placeholder="analyst, admin"
                          />
                        </label>
                        <label>
                          Token expires (min)
                          <input
                            type="number"
                            min={1}
                            value={playExpiresMin}
                            onChange={(e) => setPlayExpiresMin(Number(e.target.value) || 15)}
                          />
                        </label>
                      </>
                    )}
                  </div>
                  <div className={styles.rowGap}>
                    <button type="button" className={styles.primary} onClick={onTry} disabled={pending}>
                      Send
                    </button>
                    <button
                      type="button"
                      className={styles.secondary}
                      onClick={() => {
                        const prefix = draftSpec.app.api_prefix || "";
                        setPlayPath(`${prefix}${endpoint.path}`);
                        setPlayMethod("GET");
                        setPlayQuery("limit=5");
                      }}
                    >
                      Fill from endpoint
                    </button>
                  </div>
                  <pre className={styles.playOut}>{playResult || "Response appears here after Send."}</pre>
                  <div className={styles.rowGap}>
                    <h3 style={{ margin: 0, flex: 1 }}>curl</h3>
                    <button
                      type="button"
                      className={styles.ghostBtn}
                      onClick={() => onCopy(snippets.curl, "curl")}
                    >
                      Copy
                    </button>
                  </div>
                  <pre className={styles.yaml}>{snippets.curl}</pre>
                  <div className={styles.rowGap}>
                    <h3 style={{ margin: 0, flex: 1 }}>Python + pandas</h3>
                    <button
                      type="button"
                      className={styles.ghostBtn}
                      onClick={() => onCopy(snippets.python, "Python")}
                    >
                      Copy
                    </button>
                  </div>
                  <pre className={styles.yaml}>{snippets.python}</pre>
                </div>
              )}

              {editorTab === "yaml" && (
                <div className={styles.editorBlock}>
                  <div className={styles.rowGap}>
                    <button type="button" className={styles.secondary} onClick={onRefreshYaml}>
                      Refresh canonical YAML
                    </button>
                    <button
                      type="button"
                      className={styles.secondary}
                      onClick={() => onCopy(yamlText || localYaml, "YAML")}
                    >
                      Copy YAML
                    </button>
                  </div>
                  <pre className={styles.yaml}>{yamlText || localYaml}</pre>
                </div>
              )}
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

        <aside className={styles.panel}>
          <div className={styles.panelHead}>
            <h2>Contract</h2>
            <span>live YAML</span>
          </div>
          <div className={styles.rowGap}>
            <button
              type="button"
              className={styles.ghostBtn}
              onClick={() => onCopy(yamlText || localYaml, "YAML")}
            >
              Copy
            </button>
          </div>
          <pre className={styles.yaml}>{yamlText || localYaml}</pre>
        </aside>
      </div>
    </div>
  );
}
