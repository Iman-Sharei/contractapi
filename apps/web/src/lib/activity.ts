/** Audit events → plain words for the Activity table (who did what, on which API, when). */

export type AuditEvent = Record<string, unknown>;

const WHAT: Record<string, string> = {
  "studio.spec.activate": "Made an API live",
  "studio.spec.deactivate": "Stopped an API",
  "studio.spec.save": "Saved an API",
  "studio.spec.delete": "Deleted an API",
  "studio.spec.restore": "Restored an earlier version",
  "studio.spec.promote": "Copied an API to another environment",
  "studio.key.create": "Created an API key",
  "studio.key.revoke": "Revoked an API key",
  "studio.token.issue": "Issued a test token",
  create: "Added a row",
  "create.async": "Queued a new row",
  bulk_create: "Added rows in bulk",
  update: "Changed a row",
  delete: "Deleted a row",
  restore: "Restored a deleted row",
  "graphql.create": "Added a row (GraphQL)",
  "graphql.update": "Changed a row (GraphQL)",
  "graphql.delete": "Deleted a row (GraphQL)",
};

export function eventTime(e: AuditEvent): string {
  const raw = e.ts ?? e.timestamp;
  const date = typeof raw === "number" ? new Date(raw * 1000) : typeof raw === "string" ? new Date(raw) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : "—";
}

export function eventWhat(e: AuditEvent): string {
  const action = String(e.action ?? e.event ?? "");
  return WHAT[action] ?? (action || "—");
}

/** Who did it: a Studio user, "Studio key", or a data-API caller (key fingerprint / token subject). */
export function eventWho(e: AuditEvent): string {
  const sub = typeof e.sub === "string" ? e.sub : "";
  if (sub === "studio-key") return "Studio key";
  if (sub.startsWith("key:")) return `API key …${sub.slice(4, 10)}`;
  return sub || "—";
}

/** Where: "shop / customers #6", or the API name / key name from meta. */
export function eventWhere(e: AuditEvent): string {
  const meta = (e.meta && typeof e.meta === "object" ? e.meta : {}) as Record<string, unknown>;
  const api = (e.api as string | undefined) ?? (meta.name as string | undefined) ?? "";
  const target = typeof meta.target === "string" ? ` → ${meta.target}` : "";
  const ep = typeof e.endpoint === "string" ? ` / ${e.endpoint}` : "";
  const id = e.resource_id != null ? ` #${String(e.resource_id)}` : "";
  return `${api}${target}${ep}${id}`.replace(/^ \/ /, "") || "—";
}
