/**
 * Database connection fields ⇄ connection URL, so non-experts never type a URL by hand.
 * User and password are percent-encoded (a "@" or ":" in a password must not break the URL).
 */

export type DbFields = {
  host: string;
  port: string;
  database: string;
  user: string;
  password: string;
};

/** Kept for existing imports. */
export type PgFields = DbFields;

/** Databases you connect to with host / port / user / password. */
export type ServerDb = "postgres" | "mysql" | "sqlserver";

export const SERVER_DBS: {
  value: ServerDb;
  label: string;
  scheme: string;
  /** Demo database of docker-compose (service names as hosts). */
  demo: DbFields;
}[] = [
  {
    value: "postgres",
    label: "PostgreSQL",
    scheme: "postgresql",
    demo: { host: "db", port: "5432", database: "app", user: "postgres", password: "postgres" },
  },
  {
    value: "mysql",
    label: "MySQL",
    scheme: "mysql",
    demo: { host: "mysql", port: "3306", database: "app", user: "demo", password: "demo" },
  },
  {
    value: "sqlserver",
    label: "SQL Server",
    scheme: "mssql",
    demo: { host: "sqlserver", port: "1433", database: "master", user: "sa", password: "Demo_pass_2024!" },
  },
];

export const DEMO_PG: DbFields = SERVER_DBS[0].demo;

const SCHEME_KIND: Record<string, ServerDb> = {
  postgres: "postgres",
  postgresql: "postgres",
  mysql: "mysql",
  mariadb: "mysql",
  mssql: "sqlserver",
  sqlserver: "sqlserver",
};

export function buildDbUrl(kind: ServerDb, f: DbFields): string {
  const scheme = SERVER_DBS.find((d) => d.value === kind)!.scheme;
  const auth = f.user
    ? `${encodeURIComponent(f.user)}${f.password ? `:${encodeURIComponent(f.password)}` : ""}@`
    : "";
  const port = f.port.trim() ? `:${f.port.trim()}` : "";
  return `${scheme}://${auth}${f.host.trim()}${port}/${encodeURIComponent(f.database.trim())}`;
}

export const buildPgUrl = (f: DbFields) => buildDbUrl("postgres", f);

/** Best-effort parse of a server-database URL; null when it is not one. */
export function parseDbUrl(url: string): { kind: ServerDb; fields: DbFields } | null {
  const m = /^(\w+)(?:\+\w+)?:\/\/(?:([^:@/]*)(?::([^@/]*))?@)?([^:/?#]+)(?::(\d+))?\/([^?#]*)/.exec(url.trim());
  const kind = m ? SCHEME_KIND[m[1].toLowerCase()] : undefined;
  if (!m || !kind) return null;
  const dec = (s: string | undefined) => {
    try {
      return decodeURIComponent(s ?? "");
    } catch {
      return s ?? "";
    }
  };
  const defaultPort = SERVER_DBS.find((d) => d.value === kind)!.demo.port;
  return {
    kind,
    fields: { user: dec(m[2]), password: dec(m[3]), host: m[4], port: m[5] ?? defaultPort, database: dec(m[6]) },
  };
}

/** Postgres-only parse, kept for existing callers. */
export function parsePgUrl(url: string): DbFields | null {
  const parsed = parseDbUrl(url);
  return parsed?.kind === "postgres" ? parsed.fields : null;
}

/** Where tables live by default: `public` (Postgres), the database itself (MySQL), `dbo` (SQL Server). */
export function defaultSchema(kind: ServerDb, database: string): string {
  if (kind === "mysql") return database.trim() || "app";
  if (kind === "sqlserver") return "dbo";
  return "public";
}

/** What is missing before we can connect, in plain words (empty = ready). */
export function missingDbFields(f: DbFields): string[] {
  const out: string[] = [];
  if (!f.host.trim()) out.push("server address");
  if (!f.database.trim()) out.push("database name");
  if (!f.user.trim()) out.push("user name");
  if (f.port.trim() && !/^\d{1,5}$/.test(f.port.trim())) out.push("a numeric port");
  return out;
}

export const missingPgFields = missingDbFields;
