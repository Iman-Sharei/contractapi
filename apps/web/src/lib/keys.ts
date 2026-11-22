/** API key rows in plain words: which APIs, what it may do, its state. */
import type { ApiKeyInfo } from "./types";

const DAY = 86_400;

export function keyApis(k: Pick<ApiKeyInfo, "apis">): string {
  return k.apis.includes("*") ? "All APIs" : k.apis.join(", ");
}

export function keyAccess(k: Pick<ApiKeyInfo, "access">): string {
  return k.access === "read" ? "Read only" : "Read and change";
}

/** "Active", "Expires in 3 days", "Expired", "Revoked". */
export function keyStatus(k: Pick<ApiKeyInfo, "revoked" | "expired" | "expires_at">, nowSec = Date.now() / 1000): string {
  if (k.revoked) return "Revoked";
  if (k.expired || (k.expires_at != null && k.expires_at <= nowSec)) return "Expired";
  if (k.expires_at == null) return "Active";
  const days = Math.ceil((k.expires_at - nowSec) / DAY);
  return days <= 1 ? "Expires within a day" : `Expires in ${days} days`;
}

export function keyLastUsed(k: Pick<ApiKeyInfo, "last_used_at">, nowSec = Date.now() / 1000): string {
  if (k.last_used_at == null) return "Never used";
  const ago = Math.max(0, nowSec - k.last_used_at);
  if (ago < 3600) return "Used in the last hour";
  if (ago < DAY) return `Used ${Math.floor(ago / 3600)} h ago`;
  return `Used ${Math.floor(ago / DAY)} days ago`;
}
