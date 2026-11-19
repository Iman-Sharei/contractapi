/**
 * Postgres connection fields ⇄ connection URL, so non-experts never type a URL by hand.
 * User and password are percent-encoded (a "@" or ":" in a password must not break the URL).
 */

export type PgFields = {
  host: string;
  port: string;
  database: string;
  user: string;
  password: string;
};

/** Demo database of docker-compose (service `db`). */
export const DEMO_PG: PgFields = {
  host: "db",
  port: "5432",
  database: "app",
  user: "postgres",
  password: "postgres",
};

export function buildPgUrl(f: PgFields): string {
  const auth = f.user
    ? `${encodeURIComponent(f.user)}${f.password ? `:${encodeURIComponent(f.password)}` : ""}@`
    : "";
  const port = f.port.trim() ? `:${f.port.trim()}` : "";
  return `postgresql://${auth}${f.host.trim()}${port}/${encodeURIComponent(f.database.trim())}`;
}

/** Best-effort parse; returns null when the text is not a postgres URL. */
export function parsePgUrl(url: string): PgFields | null {
  const m = /^postgres(?:ql)?(?:\+\w+)?:\/\/(?:([^:@/]*)(?::([^@/]*))?@)?([^:/?#]+)(?::(\d+))?\/([^?#]*)/.exec(
    url.trim(),
  );
  if (!m) return null;
  const dec = (s: string | undefined) => {
    try {
      return decodeURIComponent(s ?? "");
    } catch {
      return s ?? "";
    }
  };
  return {
    user: dec(m[1]),
    password: dec(m[2]),
    host: m[3],
    port: m[4] ?? "5432",
    database: dec(m[5]),
  };
}

/** What is missing before we can connect, in plain words (empty = ready). */
export function missingPgFields(f: PgFields): string[] {
  const out: string[] = [];
  if (!f.host.trim()) out.push("server address");
  if (!f.database.trim()) out.push("database name");
  if (!f.user.trim()) out.push("user name");
  if (f.port.trim() && !/^\d{1,5}$/.test(f.port.trim())) out.push("a numeric port");
  return out;
}
