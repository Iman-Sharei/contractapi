"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import {
  activateSpec,
  deactivateSpec,
  deleteSpec,
  getApiBase,
  listActiveApis,
  listSpecs,
  loadSpec,
} from "@/lib/api";
import { AUTH_OPTIONS } from "@/lib/labels";
import type { ActiveApiMount, SpecListItem } from "@/lib/types";
import styles from "@/components/studio/flow.module.css";

function accessLabel(auth?: string) {
  return AUTH_OPTIONS.find((o) => o.value === auth)?.label.replace(" (recommended)", "") ?? "";
}

export default function StudioCatalogPage() {
  const [specs, setSpecs] = useState<SpecListItem[]>([]);
  const [live, setLive] = useState<ActiveApiMount[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [pending, startTransition] = useTransition();

  const refresh = useCallback(() => {
    startTransition(async () => {
      setLoading(true);
      try {
        const [listed, active] = await Promise.all([listSpecs(), listActiveApis()]);
        setSpecs(listed.specs);
        setLive(active.apis);
        setError(null);
      } catch (e) {
        setError(
          e instanceof Error
            ? `Could not reach the contractapi server: ${e.message}`
            : "Could not reach the contractapi server.",
        );
      } finally {
        setLoading(false);
      }
    });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const liveNames = useMemo(() => new Set(live.map((m) => m.name)), [live]);
  const savedNames = useMemo(() => new Set(specs.map((s) => s.name)), [specs]);
  const liveWithoutDesign = live.filter((m) => !savedNames.has(m.name));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = [...specs].sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0));
    if (!q) return list;
    return list.filter(
      (s) => s.name.toLowerCase().includes(q) || (s.title || "").toLowerCase().includes(q),
    );
  }, [specs, query]);

  function run(action: () => Promise<unknown>, ok: string) {
    setMessage(null);
    setError(null);
    startTransition(async () => {
      try {
        await action();
        setMessage(ok);
        refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
    });
  }

  const makeLive = (name: string) =>
    run(async () => {
      const loaded = await loadSpec(name);
      await activateSpec(loaded.spec, name);
    }, `'${name}' is live.`);

  const stop = (name: string) => {
    if (!window.confirm(`Stop '${name}'? Callers will get an error until you make it live again.`)) return;
    run(() => deactivateSpec(name), `'${name}' stopped.`);
  };

  const stopAll = () => {
    if (!window.confirm("Stop every live API?")) return;
    run(() => deactivateSpec(), "All APIs stopped.");
  };

  const remove = (name: string) => {
    if (!window.confirm(`Delete '${name}'? It is stopped and its saved design removed.`)) return;
    run(async () => {
      if (liveNames.has(name)) await deactivateSpec(name);
      await deleteSpec(name);
    }, `Deleted '${name}'.`);
  };

  return (
    <>
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>Studio</p>
        <h1 className={styles.title}>My APIs</h1>
        <p className={styles.lede}>
          Every API you designed. <strong>Live</strong> APIs answer requests at their address;{" "}
          <strong>drafts</strong> are saved but not running.
        </p>
        <div className={styles.toolbar}>
          <Link className={styles.primary} href="/studio/new">
            New API
          </Link>
          <Link className={styles.secondary} href="/studio/diff">
            Compare versions
          </Link>
          <button type="button" className={styles.ghost} onClick={refresh} disabled={pending}>
            Refresh
          </button>
          {live.length > 0 && (
            <button type="button" className={styles.danger} onClick={stopAll} disabled={pending}>
              Stop all
            </button>
          )}
        </div>
      </section>

      {(message || error) && (
        <div className={error ? styles.bannerErr : styles.bannerOk} role={error ? "alert" : "status"}>
          <span>{error ?? message}</span>
          <button type="button" className={styles.ghost} onClick={() => (error ? refresh() : setMessage(null))}>
            {error ? "Retry" : "Dismiss"}
          </button>
        </div>
      )}

      {specs.length > 6 && (
        <div className={styles.toolbar} style={{ marginBottom: 12 }}>
          <input
            className={styles.search}
            placeholder="Search by name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search APIs"
          />
        </div>
      )}

      {loading && specs.length === 0 && !error ? (
        <div className={styles.empty} aria-busy="true">
          Loading your APIs…
        </div>
      ) : filtered.length === 0 && !error ? (
        <div className={styles.empty}>
          {specs.length === 0 ? (
            <>
              No APIs yet. <Link href="/studio/new">Create your first API</Link> from a database in
              three steps.
            </>
          ) : (
            "No APIs match your search."
          )}
        </div>
      ) : (
        <div className={styles.cardGrid}>
          {filtered.map((s) => {
            const isLive = liveNames.has(s.name);
            return (
              <article key={s.name} className={styles.card} data-testid={`api-card-${s.name}`}>
                <div className={styles.cardTop}>
                  <h2 className={styles.cardTitle}>{s.title || s.name}</h2>
                  <span className={isLive ? styles.badgeLive : styles.badge}>
                    {isLive ? "Live" : "Draft"}
                  </span>
                </div>
                <p className={styles.cardMeta}>
                  {s.name} · {s.endpoint_count ?? 0} endpoint{s.endpoint_count === 1 ? "" : "s"}
                  {s.auth ? ` · ${accessLabel(s.auth)}` : ""}
                  {s.updated_at ? ` · updated ${new Date(s.updated_at * 1000).toLocaleDateString()}` : ""}
                </p>
                {isLive && (
                  <p className={styles.cardMeta}>
                    <code>{`${getApiBase()}/apis/${s.name}`}</code>
                  </p>
                )}
                <div className={styles.toolbar} style={{ margin: 0 }}>
                  <Link className={styles.secondary} href={`/studio/${encodeURIComponent(s.name)}`}>
                    Open
                  </Link>
                  {isLive ? (
                    <button type="button" className={styles.ghost} onClick={() => stop(s.name)} disabled={pending}>
                      Stop
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={styles.primary}
                      onClick={() => makeLive(s.name)}
                      disabled={pending}
                    >
                      Make live
                    </button>
                  )}
                  <button type="button" className={styles.danger} onClick={() => remove(s.name)} disabled={pending}>
                    Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {liveWithoutDesign.length > 0 && (
        <section className={styles.panel} style={{ marginTop: 18 }}>
          <h2>Running without a saved design</h2>
          <p>These APIs answer requests but have no saved design here (for example started from the command line).</p>
          <ul className={styles.chipRow}>
            {liveWithoutDesign.map((m) => (
              <li key={m.name} className={styles.chip}>
                {m.name}{" "}
                <button type="button" className={styles.ghost} onClick={() => stop(m.name)} disabled={pending}>
                  Stop
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
