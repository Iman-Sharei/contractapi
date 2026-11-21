/**
 * Studio form ⇄ spec helpers for write rules (default / fixed values, timestamps, nested writes).
 * Values are typed like YAML would read them: numbers, true/false, null, otherwise text.
 */
import type { ColumnValues, EndpointDraft, RelationDraft } from "./types";

const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;

function typed(raw: string): string | number | boolean | null {
  const v = raw.trim();
  if (v === "null") return null;
  if (v === "true" || v === "false") return v === "true";
  if (/^-?\d+(\.\d+)?$/.test(v) && !/^-?0\d/.test(v)) return Number(v);  // keep "007" as text
  return v.replace(/^"(.*)"$/, "$1");
}

/** "status = pending" lines → {status: "pending"}; problems are reported, not dropped. */
export function parseColumnValues(text: string): { values: ColumnValues; errors: string[] } {
  const values: ColumnValues = {};
  const errors: string[] = [];
  text.split("\n").forEach((line, i) => {
    if (!line.trim()) return;
    const eq = line.indexOf("=");
    const key = (eq < 0 ? line : line.slice(0, eq)).trim();
    if (eq < 0) errors.push(`Line ${i + 1}: write it as column = value`);
    else if (!IDENT.test(key)) errors.push(`Line ${i + 1}: "${key}" is not a column name`);
    else values[key] = typed(line.slice(eq + 1));
  });
  return { values, errors };
}

export function formatColumnValues(values: ColumnValues | undefined): string {
  return Object.entries(values ?? {})
    .map(([k, v]) => `${k} = ${v === null ? "null" : typeof v === "string" && typed(v) !== v ? `"${v}"` : String(v)}`)
    .join("\n");
}

/** Relations that can be created together with the parent. */
export function nestableRelations(ep: EndpointDraft): RelationDraft[] {
  return (ep.relations ?? []).filter((r) => r.type === "one_to_many");
}

export function toggleNested(ep: EndpointDraft, name: string, on: boolean): string[] {
  const cur = new Set(ep.nested_writes ?? []);
  if (on) cur.add(name);
  else cur.delete(name);
  return [...cur];
}

/** Columns the API writes itself (clients cannot send them). */
export function managedColumns(ep: EndpointDraft): string[] {
  const ts = ep.timestamps;
  return [...Object.keys(ep.fixed_values ?? {}), ...(ts?.created_at ? [ts.created_at] : []), ...(ts?.updated_at ? [ts.updated_at] : [])];
}
