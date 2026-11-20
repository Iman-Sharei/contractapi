"use client";

import { Banner, Button, Card, CardBody, CardHeader, Hint, ui } from "@/components/ui/primitives";
import { getApiBase } from "@/lib/api";
import { SERVER_DBS, type DbFields, type ServerDb } from "@/lib/dbUrl";
import styles from "../pages.module.css";

type Props = {
  kind: ServerDb;
  setKind: (k: ServerDb) => void;
  fields: DbFields;
  setField: (key: keyof DbFields, value: string) => void;
  useUrl: boolean;
  setUseUrl: (v: boolean) => void;
  dbUrl: string;
  setDbUrl: (v: string) => void;
  schema: string;
  setSchema: (v: string) => void;
  /** MySQL: the schema is the database itself (shown, not typed). Null elsewhere. */
  fixedSchema: string | null;
  apiName: string;
  setApiName: (v: string) => void;
  slug: string;
  nameTaken: boolean;
  pending: boolean;
  onConnect: () => void;
};

/** Step 1 — connect to the database with plain fields (or paste a URL). */
export function ConnectStep(p: Props) {
  const field = (key: keyof DbFields, label: string, extra: Record<string, string> = {}) => (
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
    <Card>
      <CardHeader
        icon="database"
        title="Connect your database"
        description="Studio only reads the list of tables and columns. Nothing is shared until you publish — and then only the columns you pick."
      />
      <CardBody className={ui.stack}>
        {!p.useUrl && (
          <div className={styles.modeRow}>
            <span className={styles.modeLabel}>Which database?</span>
            <div className={ui.segmented} role="group" aria-label="Database type">
              {SERVER_DBS.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  className={ui.segment}
                  aria-pressed={p.kind === d.value}
                  data-testid={`wizard-db-kind-${d.value}`}
                  onClick={() => p.setKind(d.value)}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className={styles.modeRow}>
          <span className={styles.modeLabel}>How do you want to connect?</span>
          <div className={ui.segmented} role="group" aria-label="Connection style">
            <button
              type="button"
              className={ui.segment}
              aria-pressed={!p.useUrl}
              onClick={() => p.setUseUrl(false)}
            >
              Separate fields
            </button>
            <button
              type="button"
              className={ui.segment}
              aria-pressed={p.useUrl}
              data-testid="wizard-db-url-toggle"
              onClick={() => p.setUseUrl(true)}
            >
              Connection URL
            </button>
          </div>
        </div>

        {!p.useUrl ? (
          <div className={styles.dbGrid}>
            {field("host", "Server address", { placeholder: "e.g. db.example.com" })}
            {field("port", "Port", { inputMode: "numeric" })}
            {field("database", "Database name")}
            {field("user", "User name")}
            <label className={ui.span2}>
              Password
              <input
                type="password"
                value={p.fields.password}
                onChange={(e) => p.setField("password", e.target.value)}
                autoComplete="off"
                data-testid="wizard-db-password"
              />
              <Hint>
                Stored encrypted on the server, never in your API files. Running the Docker demo? Keep
                the filled-in values.
              </Hint>
            </label>
          </div>
        ) : (
          <label>
            Connection URL
            <input
              data-testid="wizard-db-url"
              type="password"
              value={p.dbUrl}
              onChange={(e) => p.setDbUrl(e.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="postgresql://… · mysql://… · mssql://user:password@host:port/database"
            />
            <Hint>Hidden while you type. The password part is stored encrypted on the server.</Hint>
          </label>
        )}

        <hr className={styles.divider} />

        <div className={ui.formGrid}>
          <label>
            Name of this API
            <input
              data-testid="wizard-spec-name"
              value={p.apiName}
              onChange={(e) => p.setApiName(e.target.value)}
              spellCheck={false}
            />
            <Hint>
              Its address will be <code>{`${getApiBase()}/apis/${p.slug}`}</code>
            </Hint>
          </label>
          {p.fixedSchema !== null ? (
            <label>
              Database schema
              <input value={p.fixedSchema} disabled />
              <Hint>On MySQL the schema is the database itself.</Hint>
            </label>
          ) : (
            <label>
              Database schema
              <input value={p.schema} onChange={(e) => p.setSchema(e.target.value)} spellCheck={false} />
              <Hint>Leave the suggested value if you are not sure.</Hint>
            </label>
          )}
        </div>

        {p.nameTaken && (
          <Banner tone="warning" role="alert" data-testid="wizard-name-taken">
            An API named <code>{p.slug}</code> already exists. Choose another name, or publishing will
            replace it (the old version stays in its history).
          </Banner>
        )}
      </CardBody>
      <div className={styles.cardFoot}>
        <Button
          variant="primary"
          size="lg"
          icon="arrowRight"
          data-testid="wizard-introspect"
          onClick={p.onConnect}
          busy={p.pending}
          disabled={p.pending}
        >
          {p.pending ? "Connecting…" : "Connect & show tables"}
        </Button>
      </div>
    </Card>
  );
}
