"use client";

import { useEffect, useState, useTransition } from "react";
import {
  createApiKey,
  downloadOpenApi,
  downloadPostman,
  downloadSdk,
  getAudit,
  getSnapshot,
  listApiKeys,
  listHistory,
  listSpecs,
  promoteSpec,
  restoreSnapshot,
  revokeApiKey,
} from "@/lib/api";
import { copyText } from "@/lib/copy";
import type { SpecListItem } from "@/lib/types";
import styles from "@/components/studio/flow.module.css";

type KeyRow = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  revoked: boolean;
};

export default function OpsPage() {
  const [keys, setKeys] = useState<KeyRow[]>([]);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [specs, setSpecs] = useState<SpecListItem[]>([]);
  const [promoteName, setPromoteName] = useState("");
  const [env, setEnv] = useState("staging");
  const [historyName, setHistoryName] = useState("");
  const [snapshots, setSnapshots] = useState<{ id: string; path: string }[]>([]);
  const [previewYaml, setPreviewYaml] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [newKeyName, setNewKeyName] = useState("studio");
  const [keyScopes, setKeyScopes] = useState("*");
  const [revealed, setRevealed] = useState<string | null>(null);

  function setOk(msg: string) {
    setMessage(msg);
    setError(null);
  }
  function setErr(msg: string) {
    setError(msg);
    setMessage(null);
  }

  function refresh() {
    startTransition(async () => {
      try {
        const [k, a, s] = await Promise.all([listApiKeys(), getAudit(80), listSpecs()]);
        setKeys(k.keys as KeyRow[]);
        setEvents(a.events);
        setSpecs(s.specs);
        if (!promoteName && s.specs[0]) setPromoteName(s.specs[0].name);
        if (!historyName && s.specs[0]) {
          setHistoryName(s.specs[0].name);
          try {
            const h = await listHistory(s.specs[0].name);
            setSnapshots(h.snapshots);
          } catch {
            setSnapshots([]);
          }
        }
        setError(null);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Load failed");
      }
    });
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!historyName) return;
    startTransition(async () => {
      try {
        const h = await listHistory(historyName);
        setSnapshots(h.snapshots);
      } catch {
        setSnapshots([]);
      }
    });
  }, [historyName]);

  return (
    <>
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>Control plane</p>
        <h1 className={styles.title}>Ops</h1>
        <p className={styles.lede}>
          API keys, audit trail, env promote, authenticated Postman/SDK/OpenAPI exports via the
          Studio BFF (secrets never leave the Next server).
        </p>
        <div className={styles.toolbar}>
          <button type="button" className={styles.ghost} onClick={refresh} disabled={pending}>
            Refresh
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
        <h2>Data API keys</h2>
        <p>Create / revoke managed keys (also accepts env DATA_API_KEYS).</p>
        <div className={styles.toolbar}>
          <input
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            aria-label="Key name"
            style={{ borderRadius: 999, border: "1px solid var(--line)", padding: "0.55rem 0.9rem" }}
          />
          <input
            value={keyScopes}
            onChange={(e) => setKeyScopes(e.target.value)}
            aria-label="Scopes (comma-separated)"
            placeholder="scopes: * or read,write"
            style={{ borderRadius: 999, border: "1px solid var(--line)", padding: "0.55rem 0.9rem", minWidth: 180 }}
          />
          <button
            type="button"
            className={styles.primary}
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                try {
                  const scopes = keyScopes
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean);
                  const created = await createApiKey(newKeyName, scopes.length ? scopes : ["*"]);
                  setRevealed(created.key);
                  setOk(`Created key ${created.prefix}… — copy it now; it won’t show again.`);
                  refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Create failed");
                }
              })
            }
          >
            Create key
          </button>
        </div>
        {revealed && (
          <div className={styles.revealBox}>
            <pre className={styles.review}>{revealed}</pre>
            <div className={styles.toolbar}>
              <button
                type="button"
                className={styles.secondary}
                onClick={async () => {
                  const ok = await copyText(revealed);
                  setOk(ok ? "API key copied." : "Copy failed.");
                }}
              >
                Copy
              </button>
              <button type="button" className={styles.ghost} onClick={() => setRevealed(null)}>
                Dismiss key
              </button>
            </div>
          </div>
        )}
        <div className={styles.sourceList}>
          {keys.map((k) => (
            <div key={k.id} className={styles.sourceRow}>
              <span>
                <strong>{k.name}</strong> · {k.prefix}… · scopes={(k.scopes || []).join(",")}{" "}
                {k.revoked ? "(revoked)" : ""}
              </span>
              {!k.revoked && (
                <button
                  type="button"
                  className={styles.danger}
                  onClick={() => {
                    if (!window.confirm(`Revoke key ${k.prefix}…?`)) return;
                    startTransition(async () => {
                      try {
                        await revokeApiKey(k.id);
                        setOk("Key revoked.");
                        refresh();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Revoke failed");
                      }
                    });
                  }}
                >
                  Revoke
                </button>
              )}
            </div>
          ))}
          {keys.length === 0 && <p className={styles.lede}>No managed keys yet.</p>}
        </div>
      </section>

      <section className={styles.panel} style={{ marginBottom: 16 }}>
        <h2>Promote environment</h2>
        <p>
          Copies a saved spec to <code>{promoteName || "name"}_{env}</code> with env stamp.
        </p>
        <div className={styles.diffGrid}>
          <label className={styles.field}>
            Spec
            <select value={promoteName} onChange={(e) => setPromoteName(e.target.value)}>
              {specs.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            Target env
            <select value={env} onChange={(e) => setEnv(e.target.value)}>
              <option value="staging">staging</option>
              <option value="production">production</option>
              <option value="development">development</option>
            </select>
          </label>
        </div>
        <button
          type="button"
          className={styles.primary}
          disabled={pending || !promoteName}
          onClick={() => {
            const target = `${promoteName}_${env}`;
            if (!window.confirm(`Promote '${promoteName}' → '${target}'?`)) return;
            startTransition(async () => {
              try {
                const res = await promoteSpec(promoteName, env);
                setOk(`Promoted → ${res.name}`);
                refresh();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Promote failed");
              }
            });
          }}
        >
          Promote
        </button>
      </section>

      <section className={styles.panel} style={{ marginBottom: 16 }}>
        <h2>History restore</h2>
        <p>Every Save snapshots the previous YAML. Preview before restore.</p>
        <div className={styles.diffGrid}>
          <label className={styles.field}>
            Spec
            <select value={historyName} onChange={(e) => setHistoryName(e.target.value)}>
              {specs.map((s) => (
                <option key={`h-${s.name}`} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className={styles.sourceList}>
          {snapshots.map((snap) => (
            <div key={snap.id} className={styles.sourceRow}>
              <code>{snap.id}</code>
              <div className={styles.toolbar} style={{ margin: 0 }}>
                <button
                  type="button"
                  className={styles.secondary}
                  onClick={() =>
                    startTransition(async () => {
                      try {
                        const snapData = await getSnapshot(historyName, snap.id);
                        setPreviewYaml(snapData.yaml);
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Preview failed");
                      }
                    })
                  }
                >
                  Preview
                </button>
                <button
                  type="button"
                  className={styles.primary}
                  onClick={() => {
                    if (!window.confirm(`Restore ${historyName} ← ${snap.id}?`)) return;
                    startTransition(async () => {
                      try {
                        await restoreSnapshot(historyName, snap.id);
                        setOk(`Restored ${historyName} ← ${snap.id}`);
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Restore failed");
                      }
                    });
                  }}
                >
                  Restore
                </button>
              </div>
            </div>
          ))}
          {snapshots.length === 0 && (
            <p className={styles.lede}>No snapshots yet — Save a spec twice to create history.</p>
          )}
        </div>
        {previewYaml && (
          <div className={styles.revealBox}>
            <div className={styles.toolbar}>
              <strong>Snapshot preview</strong>
              <button type="button" className={styles.ghost} onClick={() => setPreviewYaml(null)}>
                Close
              </button>
              <button
                type="button"
                className={styles.secondary}
                onClick={async () => {
                  await copyText(previewYaml);
                  setOk("Snapshot YAML copied.");
                }}
              >
                Copy YAML
              </button>
            </div>
            <pre className={styles.diffOut}>{previewYaml}</pre>
          </div>
        )}
      </section>

      <section className={styles.panel} style={{ marginBottom: 16 }}>
        <h2>Exports</h2>
        <p>Downloads go through the authenticated BFF — no manual X-API-Key in the browser.</p>
        <div className={styles.sourceList}>
          {specs.map((s) => (
            <div key={s.name} className={styles.sourceRow}>
              <strong>{s.name}</strong>
              <div className={styles.toolbar} style={{ margin: 0 }}>
                <button
                  type="button"
                  className={styles.secondary}
                  disabled={pending}
                  onClick={() =>
                    startTransition(async () => {
                      try {
                        await downloadPostman(s.name);
                        setOk(`Downloaded Postman for ${s.name}`);
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Postman download failed");
                      }
                    })
                  }
                >
                  Postman
                </button>
                <button
                  type="button"
                  className={styles.secondary}
                  disabled={pending}
                  onClick={() =>
                    startTransition(async () => {
                      try {
                        await downloadSdk(s.name);
                        setOk(`Downloaded SDK for ${s.name}`);
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "SDK download failed");
                      }
                    })
                  }
                >
                  SDK.py
                </button>
                <button
                  type="button"
                  className={styles.ghost}
                  disabled={pending}
                  onClick={() =>
                    startTransition(async () => {
                      try {
                        await downloadOpenApi(s.name, "json");
                        setOk(`Downloaded OpenAPI JSON for ${s.name}`);
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "OpenAPI download failed");
                      }
                    })
                  }
                >
                  OpenAPI JSON
                </button>
                <button
                  type="button"
                  className={styles.ghost}
                  disabled={pending}
                  onClick={() =>
                    startTransition(async () => {
                      try {
                        await downloadOpenApi(s.name, "yaml");
                        setOk(`Downloaded OpenAPI YAML for ${s.name}`);
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "OpenAPI YAML failed");
                      }
                    })
                  }
                >
                  OpenAPI YAML
                </button>
              </div>
            </div>
          ))}
          {specs.length === 0 && <p className={styles.lede}>Save an API first to export.</p>}
        </div>
      </section>

      <section className={styles.panel}>
        <h2>Audit (recent)</h2>
        {events.length === 0 ? (
          <p className={styles.lede}>No events in memory yet.</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.auditTable}>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Actor / meta</th>
                </tr>
              </thead>
              <tbody>
                {events
                  .slice()
                  .reverse()
                  .map((e, i) => {
                    const ts =
                      typeof e.ts === "number"
                        ? new Date(e.ts * 1000).toLocaleString()
                        : typeof e.timestamp === "string"
                          ? e.timestamp
                          : "—";
                    const action = String(e.action ?? e.event ?? e.type ?? "—");
                    const meta = JSON.stringify(
                      Object.fromEntries(
                        Object.entries(e).filter(
                          ([k]) => !["ts", "timestamp", "action", "event", "type"].includes(k),
                        ),
                      ),
                    );
                    return (
                      <tr key={i}>
                        <td>{ts}</td>
                        <td>{action}</td>
                        <td>
                          <code>{meta.slice(0, 180)}</code>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
