import { formatApiError } from "./formatError";
import type {
  ActiveInfo,
  ApiSpecDraft,
  OpenApiDiff,
  SpecListItem,
  TableInfo,
  ValidateResult,
} from "./types";

/** Browser calls Next BFF; secrets stay server-side. */
const STUDIO_PROXY = "/api/studio";
const DATA_PROXY = "/api/data";

function publicApiBase() {
  return (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

async function studioFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${STUDIO_PROXY}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  const contentType = res.headers.get("content-type") ?? "";
  const isJson =
    contentType.includes("application/json") || contentType.includes("problem+json");
  const body = isJson ? await res.json().catch(() => null) : await res.text();

  if (!res.ok) {
    throw new Error(formatApiError(body, res.status, res.statusText));
  }
  return body as T;
}

async function studioFetchText(path: string, init?: RequestInit): Promise<string> {
  const res = await fetch(`${STUDIO_PROXY}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  const text = await res.text();
  if (!res.ok) {
    let parsed: unknown = text;
    try {
      parsed = JSON.parse(text);
    } catch {
      /* keep text */
    }
    throw new Error(formatApiError(parsed, res.status, res.statusText));
  }
  return text;
}

async function studioFetchBlob(path: string): Promise<{ blob: Blob; filename: string; contentType: string }> {
  const res = await fetch(`${STUDIO_PROXY}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text();
    let parsed: unknown = text;
    try {
      parsed = JSON.parse(text);
    } catch {
      /* keep */
    }
    throw new Error(formatApiError(parsed, res.status, res.statusText));
  }
  const cd = res.headers.get("content-disposition") || "";
  const match = /filename="?([^";]+)"?/i.exec(cd);
  const contentType = res.headers.get("content-type") || "application/octet-stream";
  return {
    blob: await res.blob(),
    filename: match?.[1] || path.split("/").pop() || "download",
    contentType,
  };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function getApiBase() {
  return publicApiBase();
}

export function getDataApiKey() {
  // Data key is injected by BFF; exposed only for curl snippets as placeholder.
  return "$DATA_API_KEY";
}

export async function studioHealth() {
  return studioFetch<{ status: string; plane?: string }>("/health");
}

export async function introspectDatabase(databaseUrl: string, schema = "public") {
  return studioFetch<{ schema: string; tables: TableInfo[]; count: number }>("/introspect", {
    method: "POST",
    body: JSON.stringify({ database_url: databaseUrl, schema }),
  });
}

export async function validateSpec(spec: ApiSpecDraft, checkDb = true) {
  return studioFetch<ValidateResult>("/validate", {
    method: "POST",
    body: JSON.stringify({ spec, check_db: checkDb }),
  });
}

export async function activateSpec(spec: ApiSpecDraft, name?: string) {
  return studioFetch<{ message: string; docs_path: string }>("/activate", {
    method: "POST",
    body: JSON.stringify({ spec, check_db: true, name: name ?? null }),
  });
}

export async function deactivateSpec(name?: string) {
  const q = name ? `?name=${encodeURIComponent(name)}` : "";
  return studioFetch<{ active: boolean; message: string }>(`/deactivate${q}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getActive() {
  return studioFetch<ActiveInfo>("/active");
}

export async function deleteSpec(name: string) {
  return studioFetch<{ deleted: boolean }>(`/specs/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export async function diffSavedSpecs(before: string, after: string) {
  return studioFetch<OpenApiDiff>(
    `/openapi/diff-specs?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`,
    { method: "POST" },
  );
}

export async function saveSpec(name: string, spec: ApiSpecDraft) {
  return studioFetch<{ saved: boolean; name: string; yaml: string }>("/specs", {
    method: "POST",
    body: JSON.stringify({ name, spec }),
  });
}

export async function listSpecs() {
  return studioFetch<{ specs: SpecListItem[] }>("/specs");
}

export async function loadSpec(name: string) {
  return studioFetch<{ name: string; spec: ApiSpecDraft; yaml: string }>(
    `/specs/${encodeURIComponent(name)}`,
  );
}

export async function diffOpenApi(before: object, after: object) {
  return studioFetch<OpenApiDiff>("/openapi/diff", {
    method: "POST",
    body: JSON.stringify({ before, after }),
  });
}

export async function previewOpenApi(spec: ApiSpecDraft) {
  return studioFetch<{ valid: boolean; openapi: object | null; errors?: string[] }>(
    "/preview-openapi",
    {
      method: "POST",
      body: JSON.stringify({ spec }),
    },
  );
}

export async function issueToken(
  roles: string[] = ["analyst"],
  sub = "studio-user",
  expiresMinutes = 15,
) {
  return studioFetch<{ access_token: string; token_type: string }>("/token", {
    method: "POST",
    body: JSON.stringify({ sub, roles, expires_minutes: expiresMinutes }),
  });
}

export async function previewSql(databaseUrl: string, sql: string) {
  return studioFetch<{ columns: string[]; count: number }>("/sql-preview", {
    method: "POST",
    body: JSON.stringify({ database_url: databaseUrl, sql }),
  });
}

export async function listApiKeys() {
  return studioFetch<{ keys: Array<Record<string, unknown>> }>("/keys");
}

export async function createApiKey(name: string, scopes: string[] = ["*"]) {
  return studioFetch<{ id: string; name: string; key: string; prefix: string; scopes: string[] }>(
    "/keys",
    { method: "POST", body: JSON.stringify({ name, scopes }) },
  );
}

export async function revokeApiKey(keyId: string) {
  return studioFetch<{ revoked: boolean }>(`/keys/${encodeURIComponent(keyId)}`, {
    method: "DELETE",
  });
}

export async function getAudit(limit = 100) {
  return studioFetch<{ events: Record<string, unknown>[] }>(`/audit?limit=${limit}`);
}

export async function listHistory(name: string) {
  return studioFetch<{ name: string; snapshots: { id: string; path: string }[] }>(
    `/specs/${encodeURIComponent(name)}/history`,
  );
}

export async function getSnapshot(name: string, snapshotId: string) {
  return studioFetch<{
    name: string;
    snapshot_id: string;
    yaml: string;
    spec?: ApiSpecDraft;
  }>(`/specs/${encodeURIComponent(name)}/history/${encodeURIComponent(snapshotId)}`);
}

export async function promoteSpec(name: string, environment: string) {
  return studioFetch<{ promoted: boolean; name: string; environment: string }>(
    `/specs/${encodeURIComponent(name)}/promote`,
    { method: "POST", body: JSON.stringify({ environment }) },
  );
}

export async function restoreSnapshot(name: string, snapshotId: string) {
  return studioFetch<{ restored: boolean; name: string; yaml: string }>(
    `/specs/${encodeURIComponent(name)}/history/${encodeURIComponent(snapshotId)}/restore`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export async function dumpYaml(spec: ApiSpecDraft): Promise<string> {
  return studioFetchText("/dump-yaml", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec }),
  });
}

export async function downloadPostman(name: string) {
  const { blob, filename } = await studioFetchBlob(
    `/specs/${encodeURIComponent(name)}/postman`,
  );
  downloadBlob(blob, filename.endsWith(".json") ? filename : `${name}.postman.json`);
}

export async function downloadSdk(name: string) {
  const { blob, filename } = await studioFetchBlob(
    `/specs/${encodeURIComponent(name)}/sdk.py`,
  );
  downloadBlob(blob, filename.endsWith(".py") ? filename : `${name}_sdk.py`);
}

export async function downloadOpenApi(name: string, format: "json" | "yaml" = "json") {
  const path =
    format === "yaml"
      ? `/specs/${encodeURIComponent(name)}/openapi.yaml`
      : `/specs/${encodeURIComponent(name)}/openapi`;
  const { blob, filename } = await studioFetchBlob(path);
  downloadBlob(
    blob,
    filename.includes(".") ? filename : `${name}.openapi.${format === "yaml" ? "yaml" : "json"}`,
  );
}

export type TryRequest = {
  method: string;
  path: string;
  query?: string;
  body?: string;
  authMode: "none" | "api_key" | "jwt";
  bearer?: string;
  accept?: string;
};

export async function tryDataRequest(req: TryRequest): Promise<{
  status: number;
  headers: Record<string, string>;
  body: string;
  ms: number;
}> {
  const clean = req.path.replace(/^\/+/, "");
  const url = `${DATA_PROXY}/${clean}${req.query ? `?${req.query}` : ""}`;
  const headers: Record<string, string> = {
    Accept: req.accept || "application/json",
  };
  if (req.authMode === "jwt" && req.bearer) headers.Authorization = `Bearer ${req.bearer}`;
  // api_key: BFF injects server DATA_API_KEY; none: still may need key depending on spec
  if (req.authMode === "api_key") headers["X-Use-Data-Key"] = "1";
  if (req.body && req.method !== "GET" && req.method !== "DELETE") {
    headers["Content-Type"] = "application/json";
  }
  const started = performance.now();
  const res = await fetch(url, {
    method: req.method,
    headers,
    body: req.body && req.method !== "GET" && req.method !== "DELETE" ? req.body : undefined,
    cache: "no-store",
  });
  const ms = Math.round(performance.now() - started);
  const text = await res.text();
  const outHeaders: Record<string, string> = {};
  res.headers.forEach((v, k) => {
    outHeaders[k] = v;
  });
  return { status: res.status, headers: outHeaders, body: text, ms };
}

export function buildClientSnippet(opts: {
  base: string;
  path: string;
  method: string;
  authMode: string;
  query?: string;
}): { curl: string; python: string } {
  const url = `${opts.base}/data${opts.path}${opts.query ? `?${opts.query}` : ""}`;
  const curlAuth =
    opts.authMode === "api_key"
      ? ` \\\n  -H "X-API-Key: $DATA_API_KEY"`
      : opts.authMode === "jwt"
        ? ` \\\n  -H "Authorization: Bearer $TOKEN"`
        : "";
  const curl = `curl -sS -X ${opts.method} "${url}"${curlAuth}`;
  const pyAuth =
    opts.authMode === "api_key"
      ? 'headers={"X-API-Key": os.environ["DATA_API_KEY"]}'
      : opts.authMode === "jwt"
        ? 'headers={"Authorization": f"Bearer {os.environ[\\"TOKEN\\"]}"}'
        : "headers={}";
  const python = `import os, httpx, pandas as pd

r = httpx.request(${JSON.stringify(opts.method)}, ${JSON.stringify(url)}, ${pyAuth})
r.raise_for_status()
data = r.json()
df = pd.DataFrame(data.get("items", data if isinstance(data, list) else [data]))
print(df.head())`;
  return { curl, python };
}

/** Local fallback YAML when dump-yaml is unavailable. Prefer dumpYaml(). */
export function buildYaml(spec: ApiSpecDraft): string {
  const lines: string[] = [];
  const app = spec.app;
  lines.push("database:");
  lines.push(`  url: ${spec.database.url}`);
  if ((spec.database as { driver?: string }).driver) {
    lines.push(`  driver: ${(spec.database as { driver?: string }).driver}`);
  }
  lines.push("app:");
  lines.push(`  title: ${JSON.stringify(app.title)}`);
  lines.push(`  version: ${app.version}`);
  lines.push(`  description: ${JSON.stringify(app.description)}`);
  lines.push(`  read_only: ${app.read_only}`);
  lines.push(`  auth: ${app.auth}`);
  lines.push(`  api_prefix: ${app.api_prefix ?? "/v1"}`);
  if (app.legacy_api_prefix) lines.push(`  legacy_api_prefix: ${app.legacy_api_prefix}`);
  if (app.environment) lines.push(`  environment: ${app.environment}`);
  lines.push(`  audit_enabled: ${app.audit_enabled ?? true}`);
  lines.push(`  compression: ${app.compression ?? true}`);
  lines.push(`  tracing: ${app.tracing ?? true}`);
  if (app.ip_allowlist?.length) {
    lines.push(`  ip_allowlist: [${app.ip_allowlist.map((x) => JSON.stringify(x)).join(", ")}]`);
  }
  if (app.webhooks?.length) {
    lines.push("  webhooks:");
    for (const wh of app.webhooks) {
      lines.push(`    - url: ${JSON.stringify(wh.url)}`);
      lines.push(`      events: [${(wh.events || []).join(", ")}]`);
      if (wh.secret) lines.push(`      secret: ${JSON.stringify(wh.secret)}`);
      if (wh.timeout_seconds != null) lines.push(`      timeout_seconds: ${wh.timeout_seconds}`);
    }
  }
  if (app.cache) {
    lines.push("  cache:");
    lines.push(`    enabled: ${app.cache.enabled}`);
    lines.push(`    ttl_seconds: ${app.cache.ttl_seconds}`);
  }
  if (app.idempotency) {
    lines.push("  idempotency:");
    lines.push(`    enabled: ${app.idempotency.enabled}`);
    lines.push(`    required_for_writes: ${app.idempotency.required_for_writes ?? false}`);
    if (app.idempotency.ttl_seconds != null) {
      lines.push(`    ttl_seconds: ${app.idempotency.ttl_seconds}`);
    }
  }
  lines.push("  rate_limit:");
  lines.push(`    enabled: ${app.rate_limit.enabled}`);
  lines.push(`    requests_per_minute: ${app.rate_limit.requests_per_minute}`);
  if (app.rbac?.length) {
    lines.push("  rbac:");
    for (const role of app.rbac) {
      lines.push(`    - role: ${role.role}`);
      lines.push("      endpoints:");
      for (const [ep, fields] of Object.entries(role.endpoints)) {
        lines.push(`        ${ep}: [${fields.join(", ")}]`);
      }
    }
  }
  lines.push("endpoints:");
  for (const ep of spec.endpoints) {
    lines.push(`  - name: ${ep.name}`);
    lines.push(`    path: ${ep.path}`);
    if (ep.sql) {
      lines.push("    sql: |");
      for (const ln of ep.sql.split("\n")) lines.push(`      ${ln}`);
      if (ep.sql_params?.length) {
        lines.push("    sql_params:");
        for (const p of ep.sql_params) {
          lines.push(`      - name: ${p.name}`);
          lines.push(`        type: ${p.type}`);
          if (p.required != null) lines.push(`        required: ${p.required}`);
          if (p.default != null) lines.push(`        default: ${JSON.stringify(p.default)}`);
        }
      }
    } else {
      lines.push(`    table: ${ep.table}`);
      lines.push(`    schema: ${ep.schema}`);
    }
    lines.push(`    methods: [${ep.methods.join(", ")}]`);
    lines.push(`    primary_key: ${ep.primary_key}`);
    lines.push(`    fields: [${ep.fields.join(", ")}]`);
    if (ep.writable_fields?.length) {
      lines.push(`    writable_fields: [${ep.writable_fields.join(", ")}]`);
    }
    lines.push(`    filters: [${ep.filters.join(", ")}]`);
    if (ep.filter_operators?.length) {
      lines.push(`    filter_operators: [${ep.filter_operators.join(", ")}]`);
    }
    if (ep.search_param !== undefined) {
      lines.push(
        ep.search_param === null
          ? "    search_param: null"
          : `    search_param: ${ep.search_param}`,
      );
    }
    lines.push(`    sortable: [${ep.sortable.join(", ")}]`);
    if (ep.etag_field) lines.push(`    etag_field: ${ep.etag_field}`);
    if (ep.soft_delete) {
      lines.push("    soft_delete:");
      lines.push(`      column: ${ep.soft_delete.column}`);
    }
    if (ep.row_level) {
      lines.push("    row_level:");
      lines.push(`      column: ${ep.row_level.column}`);
      lines.push(`      claim: ${ep.row_level.claim}`);
      lines.push(`      required: ${ep.row_level.required}`);
    }
    if (ep.validations?.length) {
      lines.push("    validations:");
      for (const v of ep.validations) {
        lines.push(`      - field: ${v.field}`);
        if (v.format) lines.push(`        format: ${v.format}`);
        if (v.min_length != null) lines.push(`        min_length: ${v.min_length}`);
        if (v.max_length != null) lines.push(`        max_length: ${v.max_length}`);
        if (v.pattern) lines.push(`        pattern: ${JSON.stringify(v.pattern)}`);
        if (v.ge != null) lines.push(`        ge: ${v.ge}`);
        if (v.le != null) lines.push(`        le: ${v.le}`);
      }
    }
    const pag = ep.pagination ?? {
      enabled: true,
      mode: "cursor" as const,
      default_limit: 20,
      max_limit: 100,
    };
    lines.push("    pagination:");
    lines.push(`      enabled: ${pag.enabled}`);
    lines.push(`      mode: ${pag.mode}`);
    lines.push(`      default_limit: ${pag.default_limit}`);
    lines.push(`      max_limit: ${pag.max_limit}`);
    if (ep.bulk_enabled != null) lines.push(`    bulk_enabled: ${ep.bulk_enabled}`);
    if (ep.async_writes) lines.push(`    async_writes: true`);
    if (ep.csv_export != null) lines.push(`    csv_export: ${ep.csv_export}`);
    if (ep.ndjson_export != null) lines.push(`    ndjson_export: ${ep.ndjson_export}`);
    if (ep.parquet_export) lines.push(`    parquet_export: true`);
    if (ep.relations?.length) {
      lines.push("    relations:");
      for (const rel of ep.relations) {
        lines.push(`      - name: ${rel.name}`);
        lines.push(`        table: ${rel.table}`);
        lines.push(`        schema: ${rel.schema}`);
        lines.push(`        type: ${rel.type}`);
        lines.push(`        local_key: ${rel.local_key}`);
        lines.push(`        foreign_key: ${rel.foreign_key}`);
        lines.push(`        primary_key: ${rel.primary_key}`);
        lines.push(`        fields: [${rel.fields.join(", ")}]`);
        lines.push(`        max_per_parent: ${rel.max_per_parent}`);
      }
    }
    if (ep.roles?.length) lines.push(`    roles: [${ep.roles.join(", ")}]`);
    if (ep.description) lines.push(`    description: ${JSON.stringify(ep.description)}`);
    if (ep.allow_sensitive) lines.push(`    allow_sensitive: true`);
    if (ep.deprecation?.deprecated) {
      lines.push("    deprecation:");
      lines.push("      deprecated: true");
      if (ep.deprecation.sunset) lines.push(`      sunset: ${ep.deprecation.sunset}`);
      if (ep.deprecation.successor) lines.push(`      successor: ${ep.deprecation.successor}`);
      if (ep.deprecation.link) lines.push(`      link: ${ep.deprecation.link}`);
    }
  }
  return lines.join("\n");
}
