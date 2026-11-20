"use client";

import { useEffect, useState, useTransition } from "react";
import {
  getApiBase,
  gitBranches,
  gitFile,
  gitStatus,
  gitTree,
  importDbt,
  oidcMe,
} from "@/lib/api";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { Icon } from "@/components/ui/Icon";
import { Banner, Button, ButtonLink, Card, CardBody, CardHeader, PageHeader, ui } from "@/components/ui/primitives";
import styles from "@/components/studio/pages.module.css";

export default function ToolsPage() {
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

  const [dbtJson, setDbtJson] = useState(
    '{\n  "models": [\n    {\n      "name": "orders",\n      "description": "Orders mart",\n      "columns": [{ "name": "id" }, { "name": "status" }]\n    }\n  ]\n}\n',
  );
  const [dbtResult, setDbtResult] = useState<string | null>(null);

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
        const payload = JSON.parse(dbtJson) as Record<string, unknown>;
        const res = await importDbt(payload);
        setDbtResult(JSON.stringify(res, null, 2));
        setOk(`Imported ${res.count} endpoint(s) from ${res.source}`);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "dbt import failed");
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
                {entries.length === 0 && <li className={styles.railEmpty}>Empty.</li>}
              </ul>
            </div>
            {filePreview != null && <CodeBlock code={filePreview.slice(0, 8000)} title="File preview" />}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            icon="table"
            title="dbt → endpoints"
            description="Paste a schema.yml (as JSON) or a manifest.json; each model becomes an endpoint draft."
          />
          <CardBody className={ui.stack}>
            <label>
              JSON
              <textarea
                rows={12}
                value={dbtJson}
                onChange={(e) => setDbtJson(e.target.value)}
                spellCheck={false}
                className={styles.monoArea}
              />
            </label>
            <div>
              <Button variant="primary" icon="arrowRight" onClick={runDbtImport} disabled={pending}>
                Import
              </Button>
            </div>
            {dbtResult && <CodeBlock code={dbtResult} title="Result" />}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
