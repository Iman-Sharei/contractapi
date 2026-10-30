/** Flatten FastAPI / RFC9457 / validation errors into a readable string. */
export function formatApiError(body: unknown, status: number, statusText: string): string {
  if (typeof body === "string" && body.trim()) return body.slice(0, 800);
  if (!body || typeof body !== "object") return statusText || `Request failed (${status})`;

  const o = body as Record<string, unknown>;
  if (typeof o.detail === "string") {
    if (typeof o.title === "string" && o.title && o.title !== o.detail) {
      return `${o.title}: ${o.detail}`;
    }
    return o.detail;
  }
  if (Array.isArray(o.detail)) {
    return o.detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const e = item as { loc?: unknown[]; msg?: string };
          const loc = Array.isArray(e.loc) ? e.loc.join(".") : "";
          return loc ? `${loc}: ${e.msg ?? JSON.stringify(item)}` : e.msg ?? JSON.stringify(item);
        }
        return String(item);
      })
      .join("; ");
  }
  if (o.detail && typeof o.detail === "object") {
    return JSON.stringify(o.detail);
  }
  if (typeof o.title === "string") {
    const d = typeof o.detail === "string" ? `: ${o.detail}` : "";
    return `${o.title}${d}`;
  }
  if (typeof o.message === "string") return o.message;
  return statusText || `Request failed (${status})`;
}
