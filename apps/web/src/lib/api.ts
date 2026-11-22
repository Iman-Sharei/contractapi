import { formatApiError } from "./formatError";
import { toYaml } from "./yaml";
import type {
  ActiveApiMount,
  ActiveInfo,
  ApiKeyInfo,
  ApiSpecDraft,
  DatabaseChanges,
  DatabaseDriver,
  EndpointDraft,
  LoginServerInfo,
  OpenApiDiff,
  SpecListItem,
  StudioHealth,
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
  return studioFetch<StudioHealth>("/health");
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

/** Activate under /apis/{name} without replacing /data (unless primary=true). */
export async function activateNamedSpec(
  spec: ApiSpecDraft,
  name: string,
  primary = false,
) {
  const q = primary ? "?primary=true" : "";
  return studioFetch<{ message: string; docs_path: string }>(
    `/activate/${encodeURIComponent(name)}${q}`,
    {
      method: "POST",
      body: JSON.stringify({ spec, check_db: true, name }),
    },
  );
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

export async function listActiveApis() {
  return studioFetch<{ count: number; apis: ActiveApiMount[] }>("/active/list");
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

export async function checkDatabaseChanges(name: string) {
  return studioFetch<DatabaseChanges>(`/specs/${encodeURIComponent(name)}/database-changes`);
}

/** What saving this draft would change for callers of the saved API. */
export async function compareDraft(name: string, spec: ApiSpecDraft) {
  return studioFetch<OpenApiDiff>(`/specs/${encodeURIComponent(name)}/compare-draft`, {
    method: "POST",
    body: JSON.stringify({ spec }),
  });
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
  claims: Record<string, string | number | boolean> = {},
  api?: string,
) {
  return studioFetch<{ access_token: string; token_type: string }>("/token", {
    method: "POST",
    body: JSON.stringify({ sub, roles, expires_minutes: expiresMinutes, claims, api: api ?? null }),
  });
}

export async function previewSql(
  databaseUrl: string,
  sql: string,
  driver: DatabaseDriver = "postgres",
) {
  return studioFetch<{ columns: string[]; count: number }>("/sql-preview", {
    method: "POST",
    body: JSON.stringify({ database_url: databaseUrl, sql, driver }),
  });
}

/** dbt schema.yml (YAML or JSON) or manifest.json text → endpoint drafts. */
export async function importDbt(text: string) {
  return studioFetch<{ source: string; count: number; endpoints: EndpointDraft[] }>("/import/dbt", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export async function gitStatus() {
  return studioFetch<{ repo: string; branch: string; sha: string; dirty: boolean }>("/git/status");
}

export async function gitBranches() {
  return studioFetch<{ repo: string; current: string; branches: string[] }>("/git/branches");
}

export async function gitTree(ref = "HEAD", path = "") {
  const params = new URLSearchParams({ ref, path });
  return studioFetch<{
    repo: string;
    ref: string;
    path: string;
    entries: { name: string; path: string; kind: string }[];
  }>(`/git/tree?${params}`);
}

export async function gitFile(path: string, ref = "HEAD") {
  const params = new URLSearchParams({ path, ref });
  return studioFetch<{
    repo: string;
    ref: string;
    path: string;
    content: string;
    truncated: boolean;
  }>(`/git/file?${params}`);
}

export async function oidcMe() {
  const base =
    process.env.NEXT_PUBLIC_API_BASE ||
    process.env.API_BASE ||
    "http://127.0.0.1:8000";
  const res = await fetch(`${base.replace(/\/$/, "")}/studio/oidc/me`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`OIDC me failed (${res.status})`);
  return res.json() as Promise<{
    authenticated: boolean;
    browser_login?: boolean;
    email?: string;
    sub?: string;
  }>;
}

export async function listApiKeys(): Promise<{ keys: ApiKeyInfo[] }> {
  return studioFetch<{ keys: ApiKeyInfo[] }>("/keys");
}

/** A key for some APIs ("*" = all), read-only or read & write, optionally expiring. Shown once. */
export async function createApiKey(
  name: string,
  opts: { apis: string[]; access: "read" | "write"; expiresInDays?: number | null },
) {
  return studioFetch<ApiKeyInfo & { key: string }>("/keys", {
    method: "POST",
    body: JSON.stringify({ name, apis: opts.apis, access: opts.access, expires_in_days: opts.expiresInDays ?? null }),
  });
}

/** Can the API server read this company login server's signing keys? */
export async function testCompanyLogin(issuer: string, jwksUrl?: string | null) {
  return studioFetch<LoginServerInfo>("/company-login/test", {
    method: "POST",
    body: JSON.stringify({ issuer, jwks_url: jwksUrl || null }),
  });
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
  /** Saved API name: requests go to /apis/<name>. */
  api?: string;
};

export async function tryDataRequest(req: TryRequest): Promise<{
  status: number;
  headers: Record<string, string>;
  body: string;
  ms: number;
}> {
  const clean = req.path.replace(/^\/+/, "");
  // Target the API being edited (/apis/<name>), not whichever API is primary under /data.
  const base = req.api ? `${DATA_PROXY}/apis/${encodeURIComponent(req.api)}` : DATA_PROXY;
  const url = `${base}/${clean}${req.query ? `?${req.query}` : ""}`;
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
  /** "/apis/<name>" (what Try it calls) or "/data" for the primary API. */
  mount?: string;
}): { curl: string; python: string } {
  const url = `${opts.base}${opts.mount ?? "/data"}${opts.path}${opts.query ? `?${opts.query}` : ""}`;
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
/** Local YAML preview of a draft contract (the server's /dump-yaml stays canonical). */
export function buildYaml(spec: ApiSpecDraft): string {
  return toYaml(spec as unknown as Record<string, unknown>);
}
