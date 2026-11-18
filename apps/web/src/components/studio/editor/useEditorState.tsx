"use client";

/** Editor state + actions for Studio's contract editor (shared by StudioShell and tabs). */
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { activateSpec, buildClientSnippet, buildYaml, dumpYaml, getApiBase, introspectDatabase, issueToken, listSpecs, loadSpec, previewSql, saveSpec, tryDataRequest, validateSpec } from "@/lib/api";
import { copyText } from "@/lib/copy";
import { defaultSafeColumns } from "@/lib/pickColumns";
import { tableKey } from "@/lib/tableKey";
import type { ApiSpecDraft, DatabaseDriver, EndpointDraft, FieldValidation, RelationDraft, RbacRoleDraft, TableInfo, ValidateResult, WebhookDraft } from "@/lib/types";
import { ALL_FILTER_OPS } from "@/lib/types";

export const emptyJwt = () => ({
  issuer: "contractapi",
  audience: "contractapi-clients",
  algorithm: "HS256",
  access_ttl_minutes: 15,
  refresh_ttl_days: 7,
});

export const PG_DEFAULT_URL = "postgresql://postgres:postgres@db:5432/app";
export const DUCKDB_DEFAULT_URL = "duckdb:///:memory:";
export const SNOWFLAKE_DEFAULT_URL = "snowflake://USER:PASSWORD@ACCOUNT/DB/SCHEMA?warehouse=WH";
export const BIGQUERY_DEFAULT_URL = "bigquery://project/dataset";

export function isWarehouseDriver(d: DatabaseDriver): boolean {
  return d === "duckdb" || d === "snowflake" || d === "bigquery";
}

export const emptySpec = (url: string, driver: DatabaseDriver = "postgres"): ApiSpecDraft => ({
  database: { url, driver },
  app: {
    title: "My Data API",
    version: "0.5.0",
    description: "Spec-first API over Postgres",
    read_only: true,
    auth: "api_key",
    api_prefix: "",
    cache: { enabled: true, ttl_seconds: 30 },
    idempotency: { enabled: true, required_for_writes: false, ttl_seconds: 86400 },
    rate_limit: { enabled: true, requests_per_minute: 120 },
    audit_enabled: true,
    compression: true,
    tracing: true,
    jwt: emptyJwt(),
    webhooks: [],
    rbac: [],
  },
  endpoints: [],
});

export function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "resource";
}

export type EditorTab = "contract" | "security" | "relations" | "sql" | "play" | "yaml";

export function useEditorState({
  initialName,
  embedded = false,
}: {
  initialName?: string;
  embedded?: boolean;
}) {
  const [dbUrl, setDbUrl] = useState(PG_DEFAULT_URL);
  const [dbDriver, setDbDriver] = useState<DatabaseDriver>("postgres");
  const [schema, setSchema] = useState("public");
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [spec, setSpec] = useState<ApiSpecDraft>(() => emptySpec(PG_DEFAULT_URL));
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
  const [contractOpen, setContractOpen] = useState(false);
  const yamlWarnOnce = useRef(false);
  const skipDirty = useRef(true);

  // Playground
  const [playMethod, setPlayMethod] = useState("GET");
  const [playPath, setPlayPath] = useState("/customers");
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
    () => ({ ...spec, database: { url: dbUrl, driver: dbDriver } }),
    [spec, dbUrl, dbDriver],
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

  const endpointPath = endpoint?.path;
  useEffect(() => {
    if (!endpointPath) return;
    setPlayPath(`${spec.app.api_prefix || ""}${endpointPath}`);
  }, [endpointPath, spec.app.api_prefix]);

  useEffect(() => {
    if (!initialName) return;
    startTransition(async () => {
      try {
        const loaded = await loadSpec(initialName);
        skipDirty.current = true;
        setSpec(loaded.spec);
        setDbUrl(loaded.spec.database.url);
        setSpecName(initialName);
        const first = loaded.spec.endpoints[0] ?? null;
        setActiveEndpoint(first?.name ?? null);
        setEditorTab("contract");
        setDirty(false);
        setMessage(`Loaded '${initialName}'.`);
        const schemaHint = first?.schema || "public";
        try {
          const intro = await introspectDatabase(loaded.spec.database.url, schemaHint);
          setTables(intro.tables);
          setSchema(schemaHint);
          const match =
            intro.tables.find((t) => t.schema === first?.schema && t.name === first?.table) ??
            intro.tables.find((t) => t.name === first?.table) ??
            intro.tables[0];
          if (match) setSelectedTable(tableKey(match));
        } catch (e) {
          setMessage(
            `Loaded '${initialName}' (introspect warning: ${
              e instanceof Error ? e.message : "failed"
            }). Re-introspect after fixing the DB URL.`,
          );
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Load failed");
      }
    });
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
    const removed = endpoint.name;
    setSpec((prev) => {
      const next = prev.endpoints.filter((e) => e.name !== removed);
      setActiveEndpoint(next[0]?.name ?? null);
      return { ...prev, endpoints: next };
    });
  }

  function onIntrospect() {
    setStatus(null);
    if (isWarehouseDriver(dbDriver)) {
      setSpec((prev) => ({ ...prev, database: { url: dbUrl, driver: dbDriver } }));
      setStatus(
        `${dbDriver}: table introspect is Postgres-only. Add a SQL/aggregate endpoint or activate with known fields.`,
      );
      return;
    }
    startTransition(async () => {
      try {
        const result = await introspectDatabase(dbUrl, schema);
        setTables(result.tables);
        if (result.tables[0]) setSelectedTable(tableKey(result.tables[0]));
        setSpec((prev) => ({ ...prev, database: { url: dbUrl, driver: "postgres" } }));
        setStatus(`Loaded ${result.count} tables/views from schema '${schema}'.`);
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Introspection failed");
      }
    });
  }

  function onDriverChange(next: DatabaseDriver) {
    setDbDriver(next);
    const defaults: Record<DatabaseDriver, string> = {
      postgres: PG_DEFAULT_URL,
      duckdb: DUCKDB_DEFAULT_URL,
      snowflake: SNOWFLAKE_DEFAULT_URL,
      bigquery: BIGQUERY_DEFAULT_URL,
    };
    let nextUrl = dbUrl;
    if (isWarehouseDriver(next) && (dbUrl.startsWith("postgresql") || dbUrl.startsWith("postgres"))) {
      nextUrl = defaults[next];
      setDbUrl(nextUrl);
      setTables([]);
      setSelectedTable(null);
    } else if (
      next === "postgres" &&
      (dbUrl.startsWith("duckdb") ||
        dbUrl.startsWith("snowflake") ||
        dbUrl.startsWith("bigquery") ||
        dbUrl === ":memory:")
    ) {
      nextUrl = PG_DEFAULT_URL;
      setDbUrl(nextUrl);
    } else if (isWarehouseDriver(next)) {
      nextUrl = defaults[next];
      setDbUrl(nextUrl);
      setTables([]);
      setSelectedTable(null);
    }
    setSchema(next === "duckdb" ? "main" : "public");
    setSpec((prev) => ({
      ...prev,
      database: { url: nextUrl, driver: next },
      app: {
        ...prev.app,
        read_only: isWarehouseDriver(next) ? true : prev.app.read_only,
      },
    }));
  }

  function addEndpointFromTable(table: TableInfo) {
    let name = slugify(table.name);
    let i = 2;
    while (spec.endpoints.some((e) => e.name === name)) {
      name = `${slugify(table.name)}_${i++}`;
    }
    const fields = defaultSafeColumns(table);
    const pk = table.primary_keys[0] ?? fields[0] ?? "id";
    const draft: EndpointDraft = {
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
      sortable: [pk, ...(fields.includes("created_at") ? ["created_at"] : [])],
      pagination: { enabled: true, mode: "cursor", default_limit: 20, max_limit: 100 },
      relations: [],
      roles: [],
      validations: [],
      bulk_enabled: true,
      async_writes: false,
      csv_export: true,
      ndjson_export: true,
      parquet_export: true,
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
    if (!endpoint) return;
    const parentName = selected?.name ?? endpoint.table;
    const fk = child.foreign_keys.find((f) => f.ref_table === parentName);
    if (!fk) {
      setStatus(null, `${child.name} does not reference ${parentName}`);
      return;
    }
    const relName = slugify(child.name);
    if (endpoint.relations?.some((r) => r.name === relName)) {
      setStatus(null, `Relation '${relName}' already exists.`);
      return;
    }
    const fields = defaultSafeColumns(child);
    const rel: RelationDraft = {
      name: relName,
      table: child.name,
      schema: child.schema,
      type: "one_to_many",
      local_key: fk.ref_column || endpoint.primary_key,
      foreign_key: fk.column,
      fields,
      primary_key: child.primary_keys[0] ?? fields[0] ?? "id",
      max_per_parent: 50,
    };
    updateEndpoint({ relations: [...(endpoint.relations ?? []), rel] });
    setStatus(`Added nested array '${relName}' on ${endpoint.path}`);
  }

  function addManyToOne(fk: { column: string; ref_table: string; ref_column: string }) {
    if (!endpoint) return;
    const target = tables.find((t) => t.name === fk.ref_table);
    if (!target) {
      setStatus(null, `Table ${fk.ref_table} not in introspected schema.`);
      return;
    }
    const relName = slugify(fk.ref_table);
    if (endpoint.relations?.some((r) => r.name === relName)) {
      setStatus(null, `Relation '${relName}' already exists.`);
      return;
    }
    const fields = defaultSafeColumns(target);
    const rel: RelationDraft = {
      name: relName,
      table: target.name,
      schema: target.schema,
      type: "many_to_one",
      local_key: fk.column,
      foreign_key: fk.ref_column || target.primary_keys[0] || "id",
      fields,
      primary_key: target.primary_keys[0] ?? fields[0] ?? "id",
      max_per_parent: 1,
    };
    updateEndpoint({ relations: [...(endpoint.relations ?? []), rel] });
    setStatus(`Added nested object '${relName}' on ${endpoint.path}`);
  }

  function updateRelation(name: string, patch: Partial<RelationDraft>) {
    if (!endpoint) return;
    updateEndpoint({
      relations: (endpoint.relations ?? []).map((r) =>
        r.name === name ? { ...r, ...patch } : r,
      ),
    });
  }

  function toggleRelationField(relName: string, field: string) {
    if (!endpoint) return;
    const rel = (endpoint.relations ?? []).find((r) => r.name === relName);
    if (!rel) return;
    const set = new Set(rel.fields);
    if (set.has(field)) {
      if (field === rel.primary_key || field === rel.foreign_key) return;
      if (set.size <= 1) return;
      set.delete(field);
    } else {
      set.add(field);
    }
    updateRelation(relName, { fields: [...set] });
  }

  function removeRelation(name: string) {
    if (!endpoint) return;
    updateEndpoint({
      relations: (endpoint.relations ?? []).filter((r) => r.name !== name),
    });
  }

  function patchWebhook(index: number, patch: Partial<WebhookDraft>) {
    const hooks = [...(spec.app.webhooks ?? [])];
    if (!hooks[index]) return;
    hooks[index] = { ...hooks[index], ...patch };
    patchApp({ webhooks: hooks });
  }

  function addWebhook() {
    const hooks = [...(spec.app.webhooks ?? [])];
    hooks.push({
      url: "",
      events: ["create", "update", "delete"],
      secret: "",
      timeout_seconds: 3,
    });
    patchApp({ webhooks: hooks });
  }

  function removeWebhook(index: number) {
    patchApp({ webhooks: (spec.app.webhooks ?? []).filter((_, i) => i !== index) });
  }

  function addRbacRole() {
    const roles = [...(spec.app.rbac ?? [])];
    let role = "analyst";
    let i = 2;
    while (roles.some((r) => r.role === role)) role = `role_${i++}`;
    const endpoints: Record<string, string[]> = {};
    for (const ep of spec.endpoints) {
      endpoints[ep.name] = [...ep.fields];
    }
    roles.push({ role, endpoints });
    patchApp({ rbac: roles });
  }

  function updateRbacRole(index: number, patch: Partial<RbacRoleDraft>) {
    const roles = [...(spec.app.rbac ?? [])];
    if (!roles[index]) return;
    roles[index] = { ...roles[index], ...patch };
    patchApp({ rbac: roles });
  }

  function removeRbacRole(index: number) {
    patchApp({ rbac: (spec.app.rbac ?? []).filter((_, i) => i !== index) });
  }

  function toggleRbacField(roleIndex: number, epName: string, field: string) {
    const roles = [...(spec.app.rbac ?? [])];
    const role = roles[roleIndex];
    if (!role) return;
    const current = new Set(role.endpoints[epName] ?? []);
    if (current.has(field)) current.delete(field);
    else current.add(field);
    roles[roleIndex] = {
      ...role,
      endpoints: { ...role.endpoints, [epName]: [...current] },
    };
    patchApp({ rbac: roles });
  }

  function addValidation() {
    if (!endpoint) return;
    const field = endpoint.fields[0] ?? "id";
    const next: FieldValidation = { field, format: "email" };
    updateEndpoint({ validations: [...(endpoint.validations ?? []), next] });
  }

  function updateValidation(index: number, patch: Partial<FieldValidation>) {
    if (!endpoint) return;
    const list = [...(endpoint.validations ?? [])];
    if (!list[index]) return;
    list[index] = { ...list[index], ...patch };
    updateEndpoint({ validations: list });
  }

  function removeValidation(index: number) {
    if (!endpoint) return;
    updateEndpoint({
      validations: (endpoint.validations ?? []).filter((_, i) => i !== index),
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
        const rawDrv = loaded.spec.database.driver || "postgres";
        const drv: DatabaseDriver =
          rawDrv === "duckdb" || rawDrv === "snowflake" || rawDrv === "bigquery"
            ? rawDrv
            : "postgres";
        setDbDriver(drv);
        setSpecName(name);
        setActiveEndpoint(loaded.spec.endpoints[0]?.name ?? null);
        setDirty(false);
        setStatus(`Loaded spec '${name}'.`);
        const schemaHint = loaded.spec.endpoints[0]?.schema || "public";
        if (isWarehouseDriver(drv)) {
          setTables([]);
          setMessage(`Loaded ${drv} spec '${name}' — use SQL/aggregate endpoints.`);
          return;
        }
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
        const result = await previewSql(dbUrl, sql, dbDriver);
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

  const parentTableName = selected?.name ?? endpoint?.table ?? null;
  const parentTable =
    tables.find((t) => t.name === (endpoint?.table ?? parentTableName)) ??
    tables.find((t) => t.name === parentTableName) ??
    null;
  const childTables = parentTableName
    ? tables.filter((t) => t.foreign_keys.some((fk) => fk.ref_table === parentTableName))
    : [];
  const parentForeignKeys = parentTable?.foreign_keys ?? [];

  return {
    initialName,
    embedded,
    dbUrl,
    setDbUrl,
    dbDriver,
    setDbDriver,
    schema,
    setSchema,
    tables,
    setTables,
    selectedTable,
    setSelectedTable,
    spec,
    setSpec,
    activeEndpoint,
    setActiveEndpoint,
    specName,
    setSpecName,
    savedNames,
    setSavedNames,
    message,
    setMessage,
    error,
    setError,
    validation,
    setValidation,
    editorTab,
    setEditorTab,
    yamlText,
    setYamlText,
    pending,
    startTransition,
    dirty,
    setDirty,
    showDbUrl,
    setShowDbUrl,
    contractOpen,
    setContractOpen,
    yamlWarnOnce,
    skipDirty,
    playMethod,
    setPlayMethod,
    playPath,
    setPlayPath,
    playQuery,
    setPlayQuery,
    playBody,
    setPlayBody,
    playBearer,
    setPlayBearer,
    playRoles,
    setPlayRoles,
    playExpiresMin,
    setPlayExpiresMin,
    playResult,
    setPlayResult,
    sqlDraft,
    setSqlDraft,
    selected,
    endpoint,
    draftSpec,
    localYaml,
    snippets,
    setStatus,
    onCopy,
    patchApp,
    updateEndpoint,
    removeEndpoint,
    onIntrospect,
    onDriverChange,
    addEndpointFromTable,
    addSqlEndpoint,
    toggleField,
    toggleMethod,
    addRelation,
    addManyToOne,
    updateRelation,
    toggleRelationField,
    removeRelation,
    patchWebhook,
    addWebhook,
    removeWebhook,
    addRbacRole,
    updateRbacRole,
    removeRbacRole,
    toggleRbacField,
    addValidation,
    updateValidation,
    removeValidation,
    onValidate,
    onActivate,
    onSave,
    onLoad,
    refreshSaved,
    onDiscoverSql,
    onRefreshYaml,
    onTry,
    parentTableName,
    parentTable,
    childTables,
    parentForeignKeys,
  };
}

export type EditorState = ReturnType<typeof useEditorState>;
