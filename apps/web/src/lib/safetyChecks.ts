/**
 * Plain-language safety review of a contract before publishing.
 * Warnings only — Studio never blocks; the server enforces the hard rules.
 */
import type { ApiSpecDraft } from "./types";

export type SafetyFinding = { level: "warn" | "info"; message: string };

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function safetyChecks(spec: ApiSpecDraft): SafetyFinding[] {
  const out: SafetyFinding[] = [];
  const app = spec.app;
  const writers = spec.endpoints.filter((e) => e.methods.some((m) => WRITE_METHODS.has(m)));

  if (app.auth === "none") {
    out.push({
      level: "warn",
      message:
        "Anyone who knows the URL can read this API (no key or login). Use “API key” unless the data is meant to be public.",
    });
  }
  if (!app.read_only && writers.length > 0) {
    out.push({
      level: "warn",
      message: `Writes are on for ${writers.map((e) => e.name).join(", ")}: callers can change data in your database.`,
    });
    if (app.auth === "none") {
      out.push({ level: "warn", message: "Writes without authentication: anyone could change or delete rows." });
    }
    for (const e of writers) {
      if (!e.row_level && app.auth === "jwt") {
        out.push({
          level: "info",
          message: `${e.name}: every signed-in user can change every row. Add row-level security to limit users to their own rows.`,
        });
      }
    }
  }
  for (const e of spec.endpoints.filter((x) => x.allow_sensitive)) {
    out.push({
      level: "warn",
      message: `${e.name} exposes columns that look sensitive (passwords, tokens, keys…). Double-check the field list.`,
    });
  }
  if (!app.rate_limit?.enabled) {
    out.push({ level: "warn", message: "Rate limit is off: one client can overload your database." });
  }
  if (!(app.api_prefix ?? "").trim() && writers.length > 0) {
    out.push({
      level: "info",
      message: "No version prefix (like /v1). Adding one now makes future breaking changes easier.",
    });
  }
  return out;
}
