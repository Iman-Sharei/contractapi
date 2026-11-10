"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import {
  activateNamedSpec,
  activateSpec,
  deactivateSpec,
  deleteSpec,
  getActive,
  getApiBase,
  listActiveApis,
  listSpecs,
  loadSpec,
  studioHealth,
} from "@/lib/api";
import type { ActiveApiMount, ActiveInfo, SpecListItem, StudioHealth } from "@/lib/types";
import styles from "@/components/studio/flow.module.css";

export default function StudioCatalogPage() {
  const [specs, setSpecs] = useState<SpecListItem[]>([]);
  const [active, setActive] = useState<ActiveInfo | null>(null);
  const [mounts, setMounts] = useState<ActiveApiMount[]>([]);
  const [health, setHealth] = useState<StudioHealth | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [query, setQuery] = useState("");
  const [pending, startTransition] = useTransition();

  const refresh = useCallback(() => {
    startTransition(async () => {
      setLoading(true);
      try {
        const [listed, act, healthRes, activeList] = await Promise.all([
          listSpecs(),
          getActive(),
          studioHealth().catch(() => null),
          listActiveApis().catch(() => ({ count: 0, apis: [] as ActiveApiMount[] })),
        ]);
        setSpecs(listed.specs);
        setActive(act);
        setMounts(activeList.apis);
        setHealth(healthRes);
        setBackendOk(healthRes?.status === "ok");
        setError(null);
      } catch (e) {
        setBackendOk(false);
        setError(e instanceof Error ? e.message : "Failed to load APIs");
        // Keep previous specs; do not pretend the catalog is empty.
      } finally {
        setLoading(false);
      }
    });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = [...specs].sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0));
    if (!q) return list;
    return list.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.title || "").toLowerCase().includes(q) ||
        (s.auth || "").toLowerCase().includes(q),
    );
  }, [specs, query]);

  function clearBanners() {
    setMessage(null);
    setError(null);
  }

  function onActivate(name: string, primary = true) {
    clearBanners();
    startTransition(async () => {
      try {
        const loaded = await loadSpec(name);
        if (primary) {
          await activateSpec(loaded.spec, name);
          setMessage(
            `Activated '${name}' as primary → ${getApiBase()}/data/docs (also /apis/${name})`,
          );
        } else {
          await activateNamedSpec(loaded.spec, name, false);
          setMessage(`Mounted '${name}' → ${getApiBase()}/apis/${name}`);
        }
        setError(null);
        refresh();
      } catch (e) {
        setMessage(null);
        setError(e instanceof Error ? e.message : "Activate failed");
      }
    });
  }

  function onDeactivate(name?: string) {
    clearBanners();
    startTransition(async () => {
      try {
        await deactivateSpec(name);
        setMessage(name ? `Deactivated '${name}'.` : "All data APIs deactivated.");
        setError(null);
        refresh();
      } catch (e) {
        setMessage(null);
        setError(e instanceof Error ? e.message : "Deactivate failed");
      }
    });
  }

  function onDelete(name: string) {
    if (!window.confirm(`Delete saved API '${name}'? This cannot be undone.`)) return;
    clearBanners();
    startTransition(async () => {
      try {
        await deleteSpec(name);
        setMessage(`Deleted '${name}'.`);
        setError(null);
        refresh();
      } catch (e) {
        setMessage(null);
        setError(e instanceof Error ? e.message : "Delete failed");
      }
    });
  }

  return (
    <>
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>Studio</p>
        <h1 className={styles.title}>My APIs</h1>
        <p className={styles.lede}>
          Saved contracts on disk. Primary data-plane under <code>/data</code>; additional mounts under{" "}
          <code>/apis/{"{name}"}</code>. Design, activate, compare, or remove — without mirroring your
          whole schema.
        </p>
        <div className={styles.toolbar}>
          <Link className={styles.primary} href="/studio/new">
            New API
          </Link>
          <Link className={styles.secondary} href="/studio/diff">
            Compare specs
          </Link>
          <button type="button" className={styles.ghost} onClick={refresh} disabled={pending}>
            Refresh
          </button>
          {active?.active && (
            <button
              type="button"
              className={styles.danger}
              onClick={() => onDeactivate()}
              disabled={pending}
            >
              Deactivate all
            </button>
          )}
          {backendOk !== null && (
            <span
              className={backendOk ? styles.badgeLive : styles.badge}
              title={backendOk ? "Studio backend reachable" : "Studio backend unreachable"}
            >
              {backendOk ? "backend ok" : "backend down"}
            </span>
          )}
          {health?.oidc ? <span className={styles.badgeLive}>OIDC</span> : null}
          {health?.job_queue ? <span className={styles.badgeLive}>queue</span> : null}
          {health?.multi_active ? <span className={styles.badge}>multi-active</span> : null}
        </div>
      </section>

      {(message || error) && (
        <div
          className={error ? styles.bannerErr : styles.bannerOk}
          role={error ? "alert" : "status"}
        >
          <span>{error ?? message}</span>
          <button type="button" className={styles.ghost} onClick={clearBanners} aria-label="Dismiss">
            Dismiss
          </button>
          {error && (
            <button type="button" className={styles.secondary} onClick={refresh}>
              Retry
            </button>
          )}
        </div>
      )}

      {mounts.length > 0 && (
        <section className={styles.panel} style={{ marginBottom: 18 }}>
          <h2>Live mounts</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {mounts.map((m) => (
              <li
                key={m.name}
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 10,
                  alignItems: "center",
                  padding: "0.55rem 0",
                  borderBottom: "1px solid var(--line-soft, #e5e7eb)",
                }}
              >
                <strong>{m.name}</strong>
                <span className={m.primary ? styles.badgeLive : styles.badge}>
                  {m.primary ? "primary /data" : "named"}
                </span>
                <span>
                  {m.title} v{m.version} · {m.endpoint_count} endpoints
                </span>
                <a
                  className={styles.ghost}
                  href={`${getApiBase()}${m.mount}/docs`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {m.mount}/docs
                </a>
                {m.primary_mount && (
                  <a
                    className={styles.ghost}
                    href={`${getApiBase()}${m.primary_mount}/docs`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    /data/docs
                  </a>
                )}
                <button
                  type="button"
                  className={styles.danger}
                  onClick={() => onDeactivate(m.name)}
                  disabled={pending}
                >
                  Unmount
                </button>
              </li>
            ))}
          </ul>
          {active?.summary && (
            <div className={styles.chipRow} style={{ marginTop: 12 }}>
              {active.summary.endpoints.map((ep) => (
                <span key={ep.name} className={styles.chipOn}>
                  {ep.methods.join("|")} {ep.path}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      <div className={styles.toolbar} style={{ marginBottom: 12 }}>
        <input
          className={styles.search}
          placeholder="Search APIs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search APIs"
        />
      </div>

      {loading && specs.length === 0 && !error ? (
        <div className={styles.empty} aria-busy="true">
          Loading APIs…
        </div>
      ) : error && specs.length === 0 ? (
        <div className={styles.empty} role="alert">
          Could not load the catalog. Check that the backend is running, then{" "}
          <button type="button" className={styles.secondary} onClick={refresh}>
            retry
          </button>
          .
        </div>
      ) : filtered.length === 0 ? (
        <div className={styles.empty}>
          {specs.length === 0 ? (
            <>
              No saved APIs yet.{" "}
              <Link href="/studio/new">Start the design wizard</Link> to introspect Postgres and
              publish a contract.
            </>
          ) : (
            "No APIs match your search."
          )}
        </div>
      ) : (
        <div className={styles.cardGrid}>
          {filtered.map((s) => {
            const isLive = active?.active && active.name === s.name;
            return (
              <article key={s.name} className={styles.card}>
                <div className={styles.cardTop}>
                  <h2 className={styles.cardTitle}>{s.title || s.name}</h2>
                  {isLive ? (
                    <span className={styles.badgeLive}>live</span>
                  ) : (
                    <span className={styles.badge}>{s.read_only ? "read-only" : "read/write"}</span>
                  )}
                </div>
                <p className={styles.cardMeta}>
                  {s.name}
                  {s.version ? ` · v${s.version}` : ""} · {s.endpoint_count ?? 0} endpoints
                  {s.auth ? ` · ${s.auth}` : ""}
                  {s.updated_at
                    ? ` · ${new Date(s.updated_at * 1000).toLocaleString()}`
                    : ""}
                </p>
                <div className={styles.toolbar} style={{ margin: 0 }}>
                  <Link className={styles.secondary} href={`/studio/${encodeURIComponent(s.name)}`}>
                    Open
                  </Link>
                  <button
                    type="button"
                    className={styles.primary}
                    onClick={() => onActivate(s.name, true)}
                    disabled={pending}
                  >
                    Activate primary
                  </button>
                  <button
                    type="button"
                    className={styles.secondary}
                    onClick={() => onActivate(s.name, false)}
                    disabled={pending}
                    title="Mount under /apis/{name} without replacing /data"
                  >
                    Mount /apis
                  </button>
                  <button
                    type="button"
                    className={styles.danger}
                    onClick={() => onDelete(s.name)}
                    disabled={pending}
                  >
                    Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
