"use client";

import { introspectDatabase } from "@/lib/api";
import { defaultSchema, parseDbUrl } from "@/lib/dbUrl";
import { defaultSafeColumns } from "@/lib/pickColumns";
import { tableKey } from "@/lib/tableKey";
import type { DatabaseDriver, EndpointDraft, TableInfo } from "@/lib/types";
import { ALL_FILTER_OPS } from "@/lib/types";
import { PG_DEFAULT_URL, MYSQL_DEFAULT_URL, SQLSERVER_DEFAULT_URL, DUCKDB_DEFAULT_URL, SNOWFLAKE_DEFAULT_URL, BIGQUERY_DEFAULT_URL, isWarehouseDriver, slugify, type EditorCore } from "./useEditorCore";

export function endpointActions(c: EditorCore) {
  const { dbUrl, setDbUrl, dbDriver, setDbDriver, schema, setSchema, setTables, setSelectedTable, spec, setSpec, setActiveEndpoint, setEditorTab, startTransition, sqlDraft, endpoint, setStatus, patchApp, updateEndpoint } = c;

  function removeEndpoint() {
    if (!endpoint) return;
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
      setSpec((prev) => ({ ...prev, database: { ...prev.database, url: dbUrl, driver: dbDriver } }));
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
        setSpec((prev) => ({ ...prev, database: { ...prev.database, url: dbUrl, driver: dbDriver } }));
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
      mysql: MYSQL_DEFAULT_URL,
      sqlserver: SQLSERVER_DEFAULT_URL,
      duckdb: DUCKDB_DEFAULT_URL,
      snowflake: SNOWFLAKE_DEFAULT_URL,
      bigquery: BIGQUERY_DEFAULT_URL,
    };
    // Keep the URL only when it already belongs to the chosen database.
    const parsed = parseDbUrl(dbUrl);
    const sameKind = parsed ? parsed.kind === next : dbUrl.startsWith(`${next}:`);
    let nextUrl = dbUrl;
    if (!sameKind) {
      nextUrl = defaults[next];
      setDbUrl(nextUrl);
      setTables([]);
      setSelectedTable(null);
    }
    const server = next === "postgres" || next === "mysql" || next === "sqlserver";
    const db = parseDbUrl(nextUrl)?.fields.database ?? "";
    setSchema(next === "duckdb" ? "main" : server ? defaultSchema(next, db) : "public");
    setSpec((prev) => ({
      ...prev,
      database: { ...prev.database, url: nextUrl, driver: next },
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
      path: `/analytics/${name.replace(/_/g, "-")}`,
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

  return { removeEndpoint, onIntrospect, onDriverChange, addEndpointFromTable, addSqlEndpoint, toggleField, toggleMethod };
}
