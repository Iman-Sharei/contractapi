/**
 * Copy-paste examples for calling a published API (curl / Python / pandas).
 * Pure functions so Studio, docs and tests share one source of truth.
 */
import type { ApiSpecDraft } from "./types";

export type SnippetInput = {
  /** Server origin, e.g. https://api.example.com */
  apiBase: string;
  /** Mount: "/data" for the primary API, "/apis/<name>" for others. */
  mount: string;
  apiPrefix?: string;
  path: string;
  auth: ApiSpecDraft["app"]["auth"];
  /** Real key if the user just created one; otherwise a placeholder. */
  apiKey?: string;
};

export function endpointUrl(i: SnippetInput): string {
  const base = i.apiBase.replace(/\/$/, "");
  const prefix = (i.apiPrefix ?? "").replace(/\/$/, "");
  return `${base}${i.mount}${prefix}${i.path}`;
}

function authHeader(i: SnippetInput): { name: string; value: string } | null {
  if (i.auth === "api_key") return { name: "X-API-Key", value: i.apiKey || "YOUR_API_KEY" };
  if (i.auth === "jwt") return { name: "Authorization", value: "Bearer YOUR_JWT" };
  return null;
}

export function curlSnippet(i: SnippetInput): string {
  const h = authHeader(i);
  const header = h ? ` \\\n  -H "${h.name}: ${h.value}"` : "";
  return `curl -s "${endpointUrl(i)}?limit=5"${header}`;
}

export function pythonSnippet(i: SnippetInput): string {
  const h = authHeader(i);
  const headers = h ? `{"${h.name}": "${h.value}"}` : "{}";
  return [
    "import httpx",
    "",
    `r = httpx.get("${endpointUrl(i)}", params={"limit": 5}, headers=${headers})`,
    "r.raise_for_status()",
    'print(r.json()["items"])',
  ].join("\n");
}

export function pandasSnippet(i: SnippetInput): string {
  const h = authHeader(i);
  const headers = h ? `{"${h.name}": "${h.value}"}` : "{}";
  return [
    "import httpx",
    "import pandas as pd",
    "",
    `url = "${endpointUrl(i)}"`,
    `headers = ${headers}`,
    "rows, params = [], {\"limit\": 100}",
    "while True:  # follow cursor pages until the end",
    "    page = httpx.get(url, params=params, headers=headers).raise_for_status().json()",
    '    rows += page["items"]',
    '    if not page.get("next_cursor"):',
    "        break",
    '    params["cursor"] = page["next_cursor"]',
    "df = pd.DataFrame(rows)",
    "print(df.head())",
  ].join("\n");
}
