import type { TableInfo } from "./types";

export function tableKey(t: Pick<TableInfo, "schema" | "name">): string {
  return `${t.schema}.${t.name}`;
}

export function parseTableKey(key: string): { schema: string; name: string } {
  const i = key.indexOf(".");
  if (i <= 0) return { schema: "public", name: key };
  return { schema: key.slice(0, i), name: key.slice(i + 1) };
}
