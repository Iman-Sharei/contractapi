"use client";

/** Editor state, derived values, effects and the base mutators every action builds on. */
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { buildClientSnippet, buildYaml, dumpYaml, getApiBase, introspectDatabase, loadSpec } from "@/lib/api";
import { copyText } from "@/lib/copy";
import { tableKey } from "@/lib/tableKey";
import type { ApiSpecDraft, DatabaseDriver, EndpointDraft, TableInfo, ValidateResult } from "@/lib/types";

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

export function useEditorCore({
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
  // Extra JWT claims for testing row-level security, e.g. {"tenant_id": "acme"}.
  const [playClaims, setPlayClaims] = useState("");
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
    playClaims,
    setPlayClaims,
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
    parentTableName,
    parentTable,
    childTables,
    parentForeignKeys,
  };
}

export type EditorCore = ReturnType<typeof useEditorCore>;
