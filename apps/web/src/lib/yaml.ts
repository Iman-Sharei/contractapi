/**
 * Minimal YAML emitter for JSON-like data (Studio's local contract preview).
 *
 * Every value round-trips: strings that YAML could misread (":", "#", "{", leading
 * spaces, true/null/numbers-as-text…) are double-quoted; multi-line text (SQL) uses a
 * literal block; null/undefined keys are omitted.
 */

type Json = string | number | boolean | null | undefined | Json[] | { [k: string]: Json };

const PLAIN = /^[A-Za-z_/][A-Za-z0-9_./-]*$/;
const RESERVED = /^(true|false|yes|no|on|off|null|y|n|~)$/i;

export function scalar(v: string | number | boolean): string {
  if (typeof v !== "string") return String(v);
  return PLAIN.test(v) && !RESERVED.test(v) ? v : JSON.stringify(v);
}

function isScalar(v: Json): v is string | number | boolean {
  return typeof v === "string" || typeof v === "number" || typeof v === "boolean";
}

function present(v: Json): boolean {
  return v !== null && v !== undefined;
}

function emitValue(key: string, v: Json, indent: string): string[] {
  const head = `${indent}${scalar(key)}:`;
  if (typeof v === "string" && v.includes("\n")) {
    const body = v.replace(/\n+$/, "").split("\n").map((l) => (l ? `${indent}  ${l}` : ""));
    return [`${head} |-`, ...body];
  }
  if (isScalar(v)) return [`${head} ${scalar(v)}`];
  if (Array.isArray(v)) {
    const items = v.filter(present);
    if (items.every(isScalar)) return [`${head} [${items.map((x) => scalar(x as string)).join(", ")}]`];
    return [head, ...items.flatMap((item) => emitListItem(item, `${indent}  `))];
  }
  const obj = v as Record<string, Json>;
  const keys = Object.keys(obj).filter((k) => present(obj[k]));
  if (keys.length === 0) return [`${head} {}`];
  return [head, ...keys.flatMap((k) => emitValue(k, obj[k], `${indent}  `))];
}

function emitListItem(item: Json, indent: string): string[] {
  if (isScalar(item)) return [`${indent}- ${scalar(item)}`];
  if (Array.isArray(item)) return [`${indent}- [${item.filter(isScalar).map((x) => scalar(x)).join(", ")}]`];
  const obj = item as Record<string, Json>;
  const keys = Object.keys(obj).filter((k) => present(obj[k]));
  if (keys.length === 0) return [`${indent}- {}`];
  const lines = keys.flatMap((k) => emitValue(k, obj[k], `${indent}  `));
  return [`${indent}- ${lines[0].trimStart()}`, ...lines.slice(1)];
}

export function toYaml(doc: Record<string, unknown>): string {
  const obj = doc as Record<string, Json>;
  return (
    Object.keys(obj)
      .filter((k) => present(obj[k]))
      .flatMap((k) => emitValue(k, obj[k], ""))
      .join("\n") + "\n"
  );
}
