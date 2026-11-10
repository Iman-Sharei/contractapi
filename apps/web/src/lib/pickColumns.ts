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
