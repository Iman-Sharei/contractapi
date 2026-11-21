"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import {
  getApiBase,
  gitBranches,
  gitFile,
  gitStatus,
  gitTree,
  importDbt,
  saveSpec,
  oidcMe,
} from "@/lib/api";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { Icon } from "@/components/ui/Icon";
import { Banner, Button, ButtonLink, Card, CardBody, CardHeader, Hint, PageHeader, ui } from "@/components/ui/primitives";
import { emptySpec, slugify } from "@/components/studio/editor/useEditorState";
import type { EndpointDraft } from "@/lib/types";
import styles from "@/components/studio/pages.module.css";

/** A dbt import has no connection yet: the user picks the real one in Settings next. */
const DBT_PLACEHOLDER_URL = "postgresql://USER@HOST:5432/DATABASE";

export default function ToolsPage() {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const [branchInfo, setBranchInfo] = useState<{
    current: string;
    branches: string[];
    repo: string;
  } | null>(null);
  const [ref, setRef] = useState("HEAD");
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<{ name: string; path: string; kind: string }[]>([]);
  const [filePreview, setFilePreview] = useState<string | null>(null);

  const [dbtText, setDbtText] = useState(
    "version: 2\nmodels:\n  - name: fct_orders\n    description: Orders mart\n    columns:\n      - name: order_id\n        tests: [unique, not_null]\n      - name: status\n",
  );
  const [dbtModels, setDbtModels] = useState<EndpointDraft[] | null>(null);
  const [dbtApiName, setDbtApiName] = useState("dbt_models");
  const [oidc, setOidc] = useState<{
    authenticated: boolean;
    browser_login?: boolean;
    email?: string;
  } | null>(null);

  function setOk(msg: string) {
    setMessage(msg);
    setError(null);
  }
  function setErr(msg: string) {
    setError(msg);
    setMessage(null);
  }

  function refreshGit() {
    startTransition(async () => {
      try {
        const [st, br] = await Promise.all([gitStatus(), gitBranches()]);
        setBranchInfo({ current: br.current, branches: br.branches, repo: br.repo });
        setRef(br.current || "HEAD");
        const tree = await gitTree(br.current || "HEAD", "");
        setEntries(tree.entries);
        setOk(`Git ${st.branch} @ ${st.sha.slice(0, 8)}${st.dirty ? " (dirty)" : ""}`);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Git failed");
      }
    });
  }

  function openPath(nextPath: string, kind: string) {
    startTransition(async () => {
      try {
        if (kind === "dir") {
          setPath(nextPath);
          const tree = await gitTree(ref, nextPath);
          setEntries(tree.entries);
          setFilePreview(null);
        } else {
          const file = await gitFile(nextPath, ref);
          setFilePreview(file.content);
          setOk(file.truncated ? `${nextPath} (truncated)` : nextPath);
        }
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Open failed");
      }
    });
  }

  function runDbtImport() {
    startTransition(async () => {
      try {
        const res = await importDbt(dbtText);
        setDbtModels(res.endpoints);
        setOk(`Found ${res.count} model${res.count === 1 ? "" : "s"} in the ${res.source === "manifest" ? "manifest" : "schema.yml"}.`);
      } catch (e) {
        setDbtModels(null);
        setErr(e instanceof Error ? e.message : "dbt import failed");
      }
    });
  }

  /** Save the models as a new, read-only API; its database is set next, in Settings. */
  function saveDbtApi() {
    const name = slugify(dbtApiName);
    startTransition(async () => {
      try {
        const draft = emptySpec(DBT_PLACEHOLDER_URL);
        draft.app.title = `${name} (from dbt)`;
        draft.app.description = "Endpoints imported from dbt models";
        draft.endpoints = dbtModels ?? [];
        await saveSpec(name, draft);
        router.push(`/studio/${encodeURIComponent(name)}?tab=settings`);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Could not save the API");
      }
    });
  }

  useEffect(() => {
    refreshGit();
    oidcMe()
      .then(setOidc)
      .catch(() => setOidc({ authenticated: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const apiBase = getApiBase();

  return (
    <>
      <PageHeader
        eyebrow="Studio"
        title="Tools"
        description="Browse the project's Git history and turn dbt models into API endpoints."
        actions={
          <Button variant="secondary" icon="refresh" onClick={refreshGit} disabled={pending}>
            Refresh Git
          </Button>
        }
      />

      {(message || error) && (
        <Banner
          tone={error ? "danger" : "success"}
          className={styles.gapBottom}
          onDismiss={() => {
            setMessage(null);
            setError(null);
          }}
        >
          {error ?? message}
        </Banner>
      )}

      <div className={styles.toolsGrid}>
        {(oidc?.browser_login || oidc?.authenticated) && (
          <Card className={styles.toolsWide}>
            <CardHeader
              icon="user"
              title="Single sign-on"
              description={
                oidc?.authenticated
                  ? `Signed in as ${oidc.email || "OIDC user"}`
                  : "Browser login is configured — sign in with your identity provider."
              }
              actions={
                <>
                  <ButtonLink
                    size="sm"
                    variant="primary"
                    href={`${apiBase}/studio/oidc/login?return_to=/studio/tools`}
                    external
                  >
                    Sign in with SSO
                  </ButtonLink>
                  <ButtonLink size="sm" variant="secondary" href={`${apiBase}/studio/oidc/logout`} external>
                    Sign out of SSO
                  </ButtonLink>
                </>
              }
            />
            <CardBody />
          </Card>
        )}

        <Card>
          <CardHeader
            icon="compare"
            title="Git browser"
            description={
              branchInfo
                ? `${branchInfo.repo} · ${branchInfo.current} · ${branchInfo.branches.length} refs`
                : "Read-only view of the repository the server runs from."
            }
          />
          <CardBody className={ui.stack}>
            <label>
              Branch or tag
              <select
                value={ref}
                onChange={(e) => {
                  const next = e.target.value;
                  setRef(next);
                  startTransition(async () => {
                    try {
                      const tree = await gitTree(next, path);
                      setEntries(tree.entries);
                      setFilePreview(null);
                    } catch (err) {
                      setErr(err instanceof Error ? err.message : "Tree failed");
                    }
                  });
                }}
              >
                {(branchInfo?.branches || ["HEAD"]).map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </label>
            <div className={styles.fileBox}>
              <div className={styles.fileBoxHead}>
                <code>/{path}</code>
                {path ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon="arrowLeft"
                    onClick={() => {
                      const parent = path.includes("/") ? path.split("/").slice(0, -1).join("/") : "";
                      openPath(parent, "dir");
                    }}
                  >
                    Up
                  </Button>
                ) : null}
              </div>
              <ul className={styles.fileList}>
                {entries.map((e) => (
                  <li key={e.path}>
                    <button type="button" onClick={() => openPath(e.path, e.kind)}>
                      <Icon name={e.kind === "dir" ? "layers" : "file"} size={14} />
                      {e.name}
                    </button>
                  </li>
                ))}
                {entries.length === 0 && (
                  <li className={styles.railEmpty}>
                    {path ? "This folder is empty." : "Nothing to show: the server does not run from a Git checkout."}
                  </li>
                )}
              </ul>
            </div>
            {filePreview != null && <CodeBlock code={filePreview.slice(0, 8000)} title="File preview" />}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            icon="table"
            title="dbt → endpoints"
            description="Paste a schema.yml or manifest.json; each model becomes a read-only endpoint."
          />
          <CardBody className={ui.stack}>
            <label>
              schema.yml or manifest.json
              <textarea
                rows={12}
                value={dbtText}
                onChange={(e) => setDbtText(e.target.value)}
                spellCheck={false}
                className={styles.monoArea}
                data-testid="dbt-text"
              />
            </label>
            <div>
              <Button variant="primary" icon="arrowRight" onClick={runDbtImport} disabled={pending} data-testid="dbt-import">
                Read models
              </Button>
            </div>
            {dbtModels && (
              <div className={ui.stack} data-testid="dbt-models">
                <ul className={styles.endpointList}>
                  {dbtModels.map((m) => (
                    <li key={m.name}>
                      <code>{m.path}</code>
                      <span className={styles.endpointMeta}>
                        {m.fields.length} fields · id: {m.primary_key}
                      </span>
                    </li>
                  ))}
                </ul>
                {dbtModels.length > 0 && (
                  <div className={styles.inlineForm}>
                    <label>
                      Name of the new API
                      <input value={dbtApiName} onChange={(e) => setDbtApiName(e.target.value)} spellCheck={false} />
                    </label>
                    <Button variant="primary" icon="plus" onClick={saveDbtApi} disabled={pending} data-testid="dbt-save">
                      Save as a new API
                    </Button>
                  </div>
                )}
                <Hint>
                  The new API is read-only and not live yet. Next, choose its database in Settings and
                  check the columns, then make it live.
                </Hint>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
