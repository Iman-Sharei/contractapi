"use client";

import type { PgFields } from "@/lib/dbUrl";
import styles from "../flow.module.css";

type Props = {
  fields: PgFields;
  setField: (key: keyof PgFields, value: string) => void;
  useUrl: boolean;
  setUseUrl: (v: boolean) => void;
  dbUrl: string;
  setDbUrl: (v: string) => void;
  schema: string;
  setSchema: (v: string) => void;
  apiName: string;
  setApiName: (v: string) => void;
  nameTaken: boolean;
  pending: boolean;
  onConnect: () => void;
};

/** Step 1 — connect to the database with plain fields (or paste a URL). */
export function ConnectStep(p: Props) {
  const field = (key: keyof PgFields, label: string, extra: Record<string, string> = {}) => (
    <label>
      {label}
      <input
        value={p.fields[key]}
        onChange={(e) => p.setField(key, e.target.value)}
        spellCheck={false}
        autoComplete="off"
        {...extra}
      />
    </label>
  );
  return (
    <section className={styles.panel}>
      <h2>Connect your database</h2>
      <p>
        Studio only reads the list of tables and columns. Nothing is shared until you publish, and
        only the columns you pick.
      </p>
      {!p.useUrl ? (
        <div className={styles.formGrid}>
          {field("host", "Server address", { placeholder: "db or pg.example.com" })}
          {field("port", "Port", { inputMode: "numeric", placeholder: "5432" })}
          {field("database", "Database name", { placeholder: "app" })}
          {field("user", "User name", { placeholder: "postgres" })}
          <label className={styles.span2}>
            Password
            <input
              type="password"
              value={p.fields.password}
              onChange={(e) => p.setField("password", e.target.value)}
              autoComplete="off"
              data-testid="wizard-db-password"
            />
            <span className={styles.hint}>
              Stored encrypted on the server, never in your API files. Running the Docker demo? Keep
              the filled-in values.
            </span>
          </label>
        </div>
      ) : (
        <label className={`${styles.field} ${styles.span2}`}>
          Connection URL
          <input
            data-testid="wizard-db-url"
            type="password"
            value={p.dbUrl}
            onChange={(e) => p.setDbUrl(e.target.value)}
            spellCheck={false}
            autoComplete="off"
            placeholder="postgresql://user:password@host:5432/database"
          />
        </label>
      )}
      <button
        type="button"
        className={styles.ghost}
        data-testid="wizard-db-url-toggle"
        onClick={() => p.setUseUrl(!p.useUrl)}
      >
        {p.useUrl ? "Use separate fields instead" : "I have a connection URL"}
      </button>

      <div className={styles.formGrid} style={{ marginTop: 16 }}>
        <label>
          Name of this API
          <input
            data-testid="wizard-spec-name"
            value={p.apiName}
            onChange={(e) => p.setApiName(e.target.value)}
            spellCheck={false}
          />
          <span className={styles.hint}>
            Lowercase letters, digits and _ — it becomes part of the address.
          </span>
        </label>
        <label>
          Database schema
          <input value={p.schema} onChange={(e) => p.setSchema(e.target.value)} spellCheck={false} />
          <span className={styles.hint}>Leave as public if you are not sure.</span>
        </label>
      </div>
      {p.nameTaken && (
        <p className={styles.warnBox} role="alert" data-testid="wizard-name-taken">
          An API named <code>{p.apiName}</code> already exists. Choose another name, or publishing
          will replace it (the old version stays in its history).
        </p>
      )}
      <div className={styles.toolbar}>
        <button
          type="button"
          className={styles.primary}
          data-testid="wizard-introspect"
          onClick={p.onConnect}
          disabled={p.pending}
        >
          {p.pending ? "Connecting…" : "Connect & show tables"}
        </button>
      </div>
    </section>
  );
}
