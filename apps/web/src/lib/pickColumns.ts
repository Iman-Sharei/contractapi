import { tableKey } from "./tableKey";
import type { TableInfo } from "./types";

/** Non-sensitive column names, ensuring primary key is included first when present. */
export function defaultSafeColumns(table: TableInfo): string[] {
  const safe = table.columns.filter((c) => !c.sensitive).map((c) => c.name);
  const pk = table.primary_keys[0] ?? safe[0];
  if (!pk) return safe;
  if (safe.includes(pk)) {
    return [pk, ...safe.filter((n) => n !== pk)];
  }
  return [pk, ...safe];
}

export function ensurePrimaryKey(fields: string[], table: TableInfo): string[] {
  const pk = table.primary_keys[0] ?? table.columns[0]?.name;
  if (!pk) return fields;
  if (fields.includes(pk)) return fields;
  return [pk, ...fields];
}

export function formatApiPath(prefix: string, path: string): string {
  const p = (prefix || "").replace(/\/+$/, "");
  const rest = path.startsWith("/") ? path : `/${path}`;
  return `${p}${rest}` || rest;
}

/** True when a picked column stores exact decimals (NUMERIC / DECIMAL / MONEY), e.g. prices. */
export function hasDecimalColumns(
  tables: TableInfo[],
  pickedKeys: string[],
  pickedColumns: Record<string, string[]>,
): boolean {
  return pickedKeys.some((key) => {
    const table = tables.find((t) => tableKey(t) === key);
    const picked = new Set(pickedColumns[key] ?? []);
    return (table?.columns ?? []).some((c) => picked.has(c.name) && /^(NUMERIC|DECIMAL|MONEY|NUMBER)\b/i.test(c.type));
  });
}

/** Tables ticked right after connecting: all of a small database, none of a big one, where
 *  publishing everything by accident would expose far more than intended. */
export const AUTO_PICK_MAX_TABLES = 5;

export function initialPicks(tables: TableInfo[]): Record<string, string[]> {
  if (tables.length > AUTO_PICK_MAX_TABLES) return {};
  return Object.fromEntries(tables.map((t) => [tableKey(t), defaultSafeColumns(t)]));
}

/** Id column, paging and allowed methods for a new endpoint. Without a single-column unique
 *  id (views, tables without a primary key) next-page links could skip rows and "change row 5"
 *  could change many rows, so such sources get page numbers and create-only writes. */
export function endpointDefaults(table: TableInfo, allowWrites: boolean, writeMethods: readonly string[]) {
  const uniqueId = table.primary_keys.length === 1;
  const pk = table.primary_keys[0] ?? table.columns.find((c) => !c.sensitive)?.name ?? "id";
  const methods = !allowWrites ? ["GET"] : uniqueId ? ["GET", ...writeMethods] : ["GET", "POST"];
  return { pk, uniqueId, mode: (uniqueId ? "cursor" : "offset") as "cursor" | "offset", methods };
}
