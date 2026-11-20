"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { activateSpec, introspectDatabase, listSpecs, saveSpec, validateSpec } from "@/lib/api";
import { ConnectStep } from "@/components/studio/wizard/ConnectStep";
import { PickStep } from "@/components/studio/wizard/PickStep";
import { PublishStep } from "@/components/studio/wizard/PublishStep";
import {
  SERVER_DBS,
  buildDbUrl,
  defaultSchema,
  missingDbFields,
  parseDbUrl,
  type DbFields,
  type ServerDb,
} from "@/lib/dbUrl";
import { DEFAULT_API_VERSION, WRITE_METHODS } from "@/lib/labels";
import { defaultPath } from "@/lib/pathRules";
import { defaultSafeColumns, ensurePrimaryKey } from "@/lib/pickColumns";
import { tableKey } from "@/lib/tableKey";
import type { ApiSpecDraft, EndpointDraft, TableInfo } from "@/lib/types";
import { ALL_FILTER_OPS } from "@/lib/types";
import { Icon } from "@/components/ui/Icon";
import { useConfirm } from "@/components/ui/feedback";
import { Banner, PageHeader, cx } from "@/components/ui/primitives";
import styles from "@/components/studio/pages.module.css";

const STEPS = ["Connect", "Choose data", "Protect & publish"] as const;

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "resource";
}

function uniqueEndpointName(base: string, used: Set<string>): string {
  let name = slugify(base);
  let i = 2;
  while (used.has(name)) name = `${slugify(base)}_${i++}`;
  used.add(name);
  return name;
}

export default function NewApiWizardPage() {
  const [step, setStep] = useState(0);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [apiName, setApiName] = useState("my_api");
  const [existingNames, setExistingNames] = useState<string[]>([]);
  const [dbKind, setDbKind] = useState<ServerDb>("postgres");
  const [fields, setFields] = useState<DbFields>(SERVER_DBS[0].demo);
  const [useUrl, setUseUrl] = useState(false);
  const [pastedUrl, setPastedUrl] = useState("");
  const [schema, setSchema] = useState("public");
  const [tables, setTables] = useState<TableInfo[]>([]);
  /** tableKey → selected column names */
  const [pickedColumns, setPickedColumns] = useState<Record<string, string[]>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [auth, setAuth] = useState<ApiSpecDraft["app"]["auth"]>("api_key");
  const [allowWrites, setAllowWrites] = useState(false);
  const [title, setTitle] = useState("My Data API");
  const [apiPrefix, setApiPrefix] = useState("");
  const confirm = useConfirm();

  useEffect(() => {
    listSpecs()
      .then((r) => {
        const names = r.specs.map((s) => s.name);
        setExistingNames(names);
        // Suggest a free default name instead of silently reusing an existing one.
        if (names.includes("my_api")) {
          let i = 2;
          while (names.includes(`my_api_${i}`)) i++;
          // Only replace the untouched default: never overwrite a name the user already typed.
          setApiName((cur) => (cur === "my_api" ? `my_api_${i}` : cur));
        }
      })
      .catch(() => setExistingNames([]));
  }, []);

  const slug = slugify(apiName);
  const nameTaken = existingNames.includes(slug);
  const parsedUrl = useUrl ? parseDbUrl(pastedUrl) : null;
  const kind: ServerDb = useUrl ? (parsedUrl?.kind ?? dbKind) : dbKind;
  const dbUrl = useUrl ? pastedUrl : buildDbUrl(dbKind, fields);
  // MySQL has no schemas inside a database: the schema is the database itself.
  const effectiveSchema =
    kind === "mysql" ? defaultSchema("mysql", (useUrl ? parsedUrl?.fields.database : fields.database) ?? "") : schema;
  const prefix = apiPrefix.trim() ? `/${apiPrefix.trim().replace(/^\/+|\/+$/g, "")}` : "";

  const pickedKeys = useMemo(
    () => Object.keys(pickedColumns).filter((k) => (pickedColumns[k]?.length ?? 0) > 0),
    [pickedColumns],
  );

  const draft = useMemo((): ApiSpecDraft => {
    const used = new Set<string>();
    const endpoints: EndpointDraft[] = [];
    for (const key of pickedKeys) {
      const table = tables.find((t) => tableKey(t) === key);
      if (!table) continue;
      const name = uniqueEndpointName(table.name, used);
      const pk = table.primary_keys[0] ?? table.columns.find((c) => !c.sensitive)?.name ?? "id";
      const fieldsPicked = ensurePrimaryKey(pickedColumns[key] ?? [], table);
      if (fieldsPicked.length === 0) continue;
      endpoints.push({
        name,
        path: defaultPath(name, prefix),
        table: table.name,
        schema: table.schema,
        methods: allowWrites ? ["GET", ...WRITE_METHODS] : ["GET"],
        primary_key: pk,
        fields: fieldsPicked,
        writable_fields: fieldsPicked.filter((f) => f !== pk),
        filters: fieldsPicked.filter((f) => f !== pk).slice(0, 3),
        filter_operators: [...ALL_FILTER_OPS],
        sortable: [pk],
        pagination: { enabled: true, mode: "cursor", default_limit: 20, max_limit: 100 },
        csv_export: true,
        ndjson_export: true,
        parquet_export: false,
        description: `Rows from ${table.name}`,
      });
    }
    return {
      database: { url: dbUrl, driver: kind },
      app: {
        title,
        version: DEFAULT_API_VERSION,
        description: "Created with the contractapi Studio wizard",
        read_only: !allowWrites,
        auth,
        api_prefix: prefix,
        cache: { enabled: true, ttl_seconds: 30 },
        idempotency: { enabled: true, required_for_writes: false, ttl_seconds: 86400 },
        rate_limit: { enabled: true, requests_per_minute: 120 },
        audit_enabled: true,
        compression: true,
        tracing: true,
        jwt: {
          issuer: "contractapi",
          audience: "contractapi-clients",
          algorithm: "HS256",
          access_ttl_minutes: 15,
          refresh_ttl_days: 7,
        },
        webhooks: [],
        rbac: [],
      },
      endpoints,
    };
  }, [pickedKeys, pickedColumns, tables, dbUrl, kind, title, allowWrites, auth, prefix]);

  function goStep(i: number) {
    if (i > 0 && tables.length === 0) {
      setError("Connect to your database first.");
      return;
    }
    if (i > 1 && pickedKeys.length === 0) {
      setError("Pick at least one table.");
      return;
    }
    setError(null);
    setMessage(null);
    setStep(i);
  }

  function onConnect() {
    setError(null);
    if (useUrl) {
      if (!parsedUrl) {
        setError(
          "That doesn't look like a database URL. Examples: postgresql://user:password@host:5432/db, " +
            "mysql://user:password@host:3306/db, mssql://user:password@host:1433/db.",
        );
        return;
      }
    } else {
      const missing = missingDbFields(fields);
      if (missing.length) {
        setError(`Please fill in the ${missing.join(", ")}.`);
        return;
      }
    }
    startTransition(async () => {
      try {
        const result = await introspectDatabase(dbUrl, effectiveSchema);
        setTables(result.tables);
        const next: Record<string, string[]> = {};
        for (const t of result.tables) next[tableKey(t)] = defaultSafeColumns(t);
        setPickedColumns(next);
        setExpanded(result.tables[0] ? tableKey(result.tables[0]) : null);
        setMessage(
          result.count
            ? `Connected — found ${result.count} table${result.count === 1 ? "" : "s"}.`
            : "Connected, but this schema has no tables.",
        );
        setStep(1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not connect to the database.");
      }
    });
  }

  function setUseUrlMode(next: boolean) {
    if (next === useUrl) return;
    // Carry what the user already typed across the two input styles.
    if (next) setPastedUrl(buildDbUrl(dbKind, fields));
    else if (parsedUrl) {
      setDbKind(parsedUrl.kind);
      setFields(parsedUrl.fields);
    }
    setUseUrl(next);
  }

  function changeKind(next: ServerDb) {
    if (next === dbKind) return;
    const before = SERVER_DBS.find((d) => d.value === dbKind)!.demo;
    const after = SERVER_DBS.find((d) => d.value === next)!.demo;
    // Untouched demo values switch to the new database's demo; typed values are kept
    // (only a default port follows the database type).
    const untouched = (Object.keys(before) as (keyof DbFields)[]).every((k) => fields[k] === before[k]);
    setFields(untouched ? after : { ...fields, port: fields.port === before.port ? after.port : fields.port });
    if (schema === defaultSchema(dbKind, fields.database)) setSchema(defaultSchema(next, after.database));
    setDbKind(next);
  }

  function toggleTable(key: string, table: TableInfo) {
    setPickedColumns((prev) => {
      if ((prev[key]?.length ?? 0) > 0) {
        const rest = { ...prev };
        delete rest[key];
        return rest;
      }
      return { ...prev, [key]: defaultSafeColumns(table) };
    });
    setExpanded(key);
  }

  function toggleColumn(key: string, table: TableInfo, col: string) {
    const pk = table.primary_keys[0];
    setPickedColumns((prev) => {
      const cur = prev[key] ?? [];
      if (cur.includes(col)) {
        if (col === pk) return prev; // the unique id is always part of the API
        const next = cur.filter((c) => c !== col);
        if (next.length === 0) {
          const rest = { ...prev };
          delete rest[key];
          return rest;
        }
        return { ...prev, [key]: next };
      }
      return { ...prev, [key]: ensurePrimaryKey([...cur, col], table) };
    });
  }

  function selectAllColumns(key: string, table: TableInfo, safeOnly: boolean) {
    const cols = table.columns.filter((c) => (safeOnly ? !c.sensitive : true)).map((c) => c.name);
    setPickedColumns((prev) => ({ ...prev, [key]: ensurePrimaryKey(cols, table) }));
  }

  async function onPublish(live: boolean) {
    setError(null);
    if (!/^[a-z][a-z0-9_-]{0,63}$/.test(slug)) {
      setError("The API name must start with a letter and use only lowercase letters, digits and _.");
      return;
    }
    if (draft.endpoints.length === 0) {
      setError("Pick at least one table before publishing.");
      return;
    }
    if (
      nameTaken &&
      !(await confirm({
        title: `Replace the existing API '${slug}'?`,
        body: "Its current version stays in the history, so you can restore it later.",
        confirmLabel: "Replace it",
      }))
    ) {
      return;
    }
    startTransition(async () => {
      try {
        const check = await validateSpec(draft, true);
        if (!check.valid) {
          setError(check.errors.join(" "));
          return;
        }
        await saveSpec(slug, draft);
        if (live) await activateSpec(draft, slug);
        // Full navigation: the API page loads fresh state (and shows the success banner).
        window.location.assign(`/studio/${encodeURIComponent(slug)}${live ? "?published=1" : "?saved=1"}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Publishing failed.");
      }
    });
  }

  return (
    <div className={styles.wizard}>
      <PageHeader
        eyebrow="New API"
        title="Create an API from your database"
        description="Three steps, no code: connect, choose the data to share, then protect and publish."
      />

      <ol className={styles.stepper} aria-label="Wizard steps">
        {STEPS.map((label, i) => (
          <li key={label} className={cx(styles.stepItem, i === step && styles.stepCurrent, i < step && styles.stepDone)}>
            <button type="button" onClick={() => goStep(i)} aria-current={i === step ? "step" : undefined}>
              <span className={styles.stepNum}>{i < step ? <Icon name="check" size={14} /> : i + 1}</span>
              <span className={styles.stepLabel}>{label}</span>
            </button>
          </li>
        ))}
      </ol>

      {(message || error) && (
        <Banner
          tone={error ? "danger" : "success"}
          className={styles.gapBottom}
          onDismiss={() => {
            setError(null);
            setMessage(null);
          }}
        >
          {error ?? message}
        </Banner>
      )}

      {step === 0 && (
        <ConnectStep
          fields={fields}
          setField={(k, v) => setFields((f) => ({ ...f, [k]: v }))}
          kind={dbKind}
          setKind={changeKind}
          useUrl={useUrl}
          setUseUrl={setUseUrlMode}
          dbUrl={pastedUrl}
          setDbUrl={setPastedUrl}
          schema={schema}
          setSchema={setSchema}
          fixedSchema={kind === "mysql" ? effectiveSchema : null}
          apiName={apiName}
          setApiName={setApiName}
          slug={slug}
          nameTaken={nameTaken}
          pending={pending}
          onConnect={onConnect}
        />
      )}
      {step === 1 && (
        <PickStep
          tables={tables}
          pickedColumns={pickedColumns}
          expanded={expanded}
          setExpanded={setExpanded}
          toggleTable={toggleTable}
          toggleColumn={toggleColumn}
          selectAllColumns={selectAllColumns}
          canContinue={pickedKeys.length > 0}
          onBack={() => setStep(0)}
          onContinue={() => goStep(2)}
        />
      )}
      {step === 2 && (
        <PublishStep
          draft={draft}
          title={title}
          setTitle={setTitle}
          prefix={apiPrefix}
          setPrefix={setApiPrefix}
          auth={auth}
          setAuth={setAuth}
          allowWrites={allowWrites}
          setAllowWrites={setAllowWrites}
          apiName={slug}
          nameTaken={nameTaken}
          pending={pending}
          onBack={() => setStep(1)}
          onPublish={onPublish}
        />
      )}
    </div>
  );
}
