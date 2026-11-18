/**
 * URL path rules — mirror of backend `spec.PATH_RE` / `RESERVED_PATH_SEGMENTS`
 * so Studio can explain a bad path before the server rejects it.
 */

export const PATH_RE = /^(\/[a-z0-9][a-z0-9_-]*)+$/;
export const RESERVED_SEGMENTS = new Set([
  "health",
  "ready",
  "metrics",
  "docs",
  "redoc",
  "openapi.json",
  "auth",
  "jobs",
  "graphql",
]);

/** Plain-language problem with a path, or null when it is fine. */
export function pathError(path: string, apiPrefix: string): string | null {
  const p = path.trim().replace(/\/+$/, "");
  if (!PATH_RE.test(p)) {
    return `Use lowercase letters, digits, "-" or "_" separated by "/" — e.g. ${suggestPath(p)}`;
  }
  const first = p.split("/")[1];
  if (!apiPrefix.trim() && RESERVED_SEGMENTS.has(first)) {
    return `"/${first}" is a built-in route. Try /${first}-data, or set an API prefix like /v1.`;
  }
  return null;
}

/** Turn free text into a valid path ("Order Items" → "/order-items"). */
export function suggestPath(value: string): string {
  const joined = value
    .split("/")
    .map((s) =>
      s
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, "-")
        .replace(/^[-_]+|[-_]+$/g, ""),
    )
    .filter(Boolean)
    .join("/");
  return joined ? `/${joined}` : "/items";
}

/** Default endpoint path for a table/endpoint name that never collides with system routes. */
export function defaultPath(name: string, apiPrefix: string): string {
  const path = suggestPath(name);
  return pathError(path, apiPrefix) ? `${path}-data` : path;
}
