/** Breaking changes of an OpenAPI diff, as short sentences a non-expert can judge. */
import type { OpenApiDiff } from "./types";

/** "?email__gte" and "?email" are one filter for a reader: keep the base name once. */
function group(fields: string[]): string[] {
  return [...new Set(fields.map((f) => (f.startsWith("?") ? f.split("__")[0] : f)))];
}

function describe(field: string): string {
  if (field.startsWith("?")) return `filter ${field}`;
  if (field.startsWith("body: ")) return `input field ${field.slice(6)}`;
  return `field ${field}`;
}

export function breakingLines(diff: OpenApiDiff, max = 8): string[] {
  const lines: string[] = [];
  for (const c of diff.changes) {
    if (c.type === "DELETE") lines.push(`${c.method} ${c.path} is removed`);
    else if (c.type === "UPDATE" && c.breaking && c.removed_fields?.length)
      lines.push(`${c.method} ${c.path} no longer has ${group(c.removed_fields).map(describe).join(", ")}`);
  }
  return lines.length > max ? [...lines.slice(0, max), `…and ${lines.length - max} more`] : lines;
}
