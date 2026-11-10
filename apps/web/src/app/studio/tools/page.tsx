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
import { copyText } from "@/lib/copy";
import styles from "@/components/studio/flow.module.css";

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
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>Studio</p>
        <h1 className={styles.title}>Tools</h1>
        <p className={styles.lede}>
          Git branch browser, dbt model → endpoint helper, and OIDC cookie login.
        </p>
        <div className={styles.toolbar}>
          <button type="button" className={styles.ghost} onClick={refreshGit} disabled={pending}>
            Refresh git
          </button>
        </div>
      </section>

      {(message || error) && (
        <div className={error ? styles.bannerErr : styles.bannerOk} role={error ? "alert" : "status"}>
          <span>{error ?? message}</span>
          <button
            type="button"
            className={styles.ghost}
            onClick={() => {
              setMessage(null);
              setError(null);
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      <section className={styles.panel} style={{ marginBottom: 16 }}>
        <h2>OIDC browser login</h2>
        <p>
          {oidc?.authenticated
            ? `Signed in as ${oidc.email || "OIDC user"}`
            : oidc?.browser_login
              ? "Browser login configured — use the login link below."
              : "Set STUDIO_OIDC_CLIENT_ID + REDIRECT_URI for cookie login (Bearer JWKS still works)."}
        </p>
        <div className={styles.toolbar}>
          <a className={styles.primary} href={`${apiBase}/studio/oidc/login?return_to=/studio/tools`}>
            Login with OIDC
          </a>
          <a className={styles.secondary} href={`${apiBase}/studio/oidc/logout`}>
            Logout
          </a>
        </div>
      </section>

      <section className={styles.panel} style={{ marginBottom: 16 }}>
        <h2>Git browser</h2>
        {branchInfo && (
          <p>
            {branchInfo.repo} · {branchInfo.current} · {branchInfo.branches.length} refs
          </p>
        )}
        <label className={styles.field}>
          <span>Ref</span>
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
        <p>
          Path: <code>{path || "/"}</code>{" "}
          {path ? (
            <button
              type="button"
              className={styles.ghost}
              onClick={() => {
                const parent = path.includes("/") ? path.split("/").slice(0, -1).join("/") : "";
                openPath(parent, "dir");
              }}
            >
              Up
            </button>
          ) : null}
        </p>
        <ul>
          {entries.map((e) => (
            <li key={e.path}>
              <button type="button" className={styles.ghost} onClick={() => openPath(e.path, e.kind)}>
                {e.kind === "dir" ? "[dir] " : ""}
                {e.name}
              </button>
            </li>
          ))}
        </ul>
        {filePreview != null && (
          <div>
            <button type="button" className={styles.secondary} onClick={() => copyText(filePreview)}>
              Copy file
            </button>
            <pre style={{ maxHeight: 360, overflow: "auto", fontSize: 12 }}>{filePreview.slice(0, 8000)}</pre>
          </div>
        )}
      </section>

      <section className={styles.panel}>
        <h2>dbt → endpoints</h2>
        <p>Paste schema.yml JSON or a manifest.json document.</p>
        <label className={styles.field}>
          <span>JSON</span>
          <textarea
            rows={12}
            value={dbtJson}
            onChange={(e) => setDbtJson(e.target.value)}
            spellCheck={false}
          />
        </label>
        <div className={styles.toolbar}>
          <button type="button" className={styles.primary} onClick={runDbtImport} disabled={pending}>
            Import
          </button>
        </div>
        {dbtResult && (
          <pre style={{ maxHeight: 360, overflow: "auto", fontSize: 12 }}>{dbtResult}</pre>
        )}
      </section>
    </>
  );
}
