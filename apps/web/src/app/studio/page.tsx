"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { Icon } from "@/components/ui/Icon";
import { useConfirm, useToast } from "@/components/ui/feedback";
import { Badge, Banner, Button, ButtonLink, EmptyState, PageHeader } from "@/components/ui/primitives";
import { copyText } from "@/lib/copy";
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
import styles from "@/components/studio/pages.module.css";

function accessLabel(auth?: string) {
  return AUTH_OPTIONS.find((o) => o.value === auth)?.label.replace(" (recommended)", "") ?? "";
}

export default function StudioCatalogPage() {
  const [specs, setSpecs] = useState<SpecListItem[]>([]);
  const [live, setLive] = useState<ActiveApiMount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [pending, startTransition] = useTransition();
  const confirm = useConfirm();
  const toast = useToast();

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
  const endpointTotal = specs.reduce((n, s) => n + (s.endpoint_count ?? 0), 0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = [...specs].sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0));
    if (!q) return list;
    return list.filter(
      (s) => s.name.toLowerCase().includes(q) || (s.title || "").toLowerCase().includes(q),
    );
  }, [specs, query]);

  function run(action: () => Promise<unknown>, ok: string) {
    setError(null);
    startTransition(async () => {
      try {
        await action();
        toast(ok);
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

  async function stop(name: string) {
    const ok = await confirm({
      title: `Stop '${name}'?`,
      body: "Callers get an error until you make it live again. Its design stays saved.",
      confirmLabel: "Stop API",
    });
    if (ok) run(() => deactivateSpec(name), `'${name}' stopped.`);
  }

  async function stopAll() {
    const ok = await confirm({
      title: "Stop every live API?",
      body: `${live.length} API${live.length === 1 ? "" : "s"} will stop answering requests. Saved designs are kept.`,
      confirmLabel: "Stop all",
    });
    if (ok) run(() => deactivateSpec(), "All APIs stopped.");
  }

  async function remove(name: string) {
    const ok = await confirm({
      title: `Delete '${name}'?`,
      body: "It stops answering requests and its saved design is removed. This can't be undone.",
      confirmLabel: "Delete API",
    });
    if (!ok) return;
    run(async () => {
      if (liveNames.has(name)) await deactivateSpec(name);
      await deleteSpec(name);
    }, `Deleted '${name}'.`);
  }

  async function copyAddress(url: string) {
    toast((await copyText(url)) ? "Address copied." : "Could not copy.", "success");
  }

  return (
    <>
      <PageHeader
        eyebrow="Studio"
        title="My APIs"
        description={
          <>
            Every API you designed. <strong>Live</strong> APIs answer requests at their address;{" "}
            <strong>drafts</strong> are saved but not running.
          </>
        }
        actions={
          <>
            <Button variant="ghost" icon="refresh" onClick={refresh} disabled={pending} aria-label="Refresh" />
            {live.length > 0 && (
              <Button variant="secondary" icon="stop" onClick={stopAll} disabled={pending}>
                Stop all
              </Button>
            )}
            <ButtonLink href="/studio/new" variant="primary" icon="plus">
              New API
            </ButtonLink>
          </>
        }
      />

      {error && (
        <Banner tone="danger" className={styles.gapBottom}>
          {error}{" "}
          <button type="button" className={styles.inlineLink} onClick={refresh}>
            Retry
          </button>
        </Banner>
      )}

      {specs.length > 0 && (
        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statLabel}>
              <span className={styles.liveDot} aria-hidden /> Live
            </span>
            <strong>{live.length}</strong>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Drafts</span>
            <strong>{specs.filter((s) => !liveNames.has(s.name)).length}</strong>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Endpoints</span>
            <strong>{endpointTotal}</strong>
          </div>
        </div>
      )}

      {specs.length > 6 && (
        <div className={styles.search}>
          <Icon name="search" />
          <input
            placeholder="Search by name or title…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search APIs"
          />
        </div>
      )}

      {loading && specs.length === 0 && !error ? (
        <div className={styles.cardGrid} aria-busy="true" aria-label="Loading your APIs">
          {[0, 1, 2].map((i) => (
            <div key={i} className={styles.skeleton} />
          ))}
        </div>
      ) : filtered.length === 0 && !error ? (
        specs.length === 0 ? (
          <EmptyState
            icon="database"
            title="No APIs yet"
            action={
              <ButtonLink href="/studio/new" variant="primary" icon="plus">
                Create your first API
              </ButtonLink>
            }
          >
            Connect a database, pick the tables to share and publish — three steps, no code.
          </EmptyState>
        ) : (
          <EmptyState icon="search" title="No APIs match your search" />
        )
      ) : (
        <div className={styles.cardGrid}>
          {filtered.map((s) => {
            const isLive = liveNames.has(s.name);
            const address = `${getApiBase()}/apis/${s.name}`;
            return (
              <article key={s.name} className={styles.apiCard} data-testid={`api-card-${s.name}`}>
                <div className={styles.apiCardTop}>
                  <span className={styles.apiIcon} aria-hidden>
                    <Icon name="database" size={18} />
                  </span>
                  <div className={styles.apiCardName}>
                    <Link href={`/studio/${encodeURIComponent(s.name)}`} className={styles.apiCardLink}>
                      {s.title || s.name}
                    </Link>
                    <span className={styles.apiCardSlug}>{s.name}</span>
                  </div>
                  <Badge tone={isLive ? "success" : "neutral"} dot pulse={isLive}>
                    {isLive ? "Live" : "Draft"}
                  </Badge>
                </div>
                <div className={styles.metaRow}>
                  <span>
                    <Icon name="layers" size={14} /> {s.endpoint_count ?? 0} endpoint
                    {s.endpoint_count === 1 ? "" : "s"}
                  </span>
                  {s.auth && (
                    <span>
                      <Icon name={s.auth === "none" ? "globe" : "lock"} size={14} /> {accessLabel(s.auth)}
                    </span>
                  )}
                  {s.updated_at ? (
                    <span>Updated {new Date(s.updated_at * 1000).toLocaleDateString()}</span>
                  ) : null}
                </div>
                {isLive ? (
                  <button
                    type="button"
                    className={styles.address}
                    onClick={() => copyAddress(address)}
                    title="Copy address"
                  >
                    <code>{address}</code>
                    <Icon name="copy" size={14} />
                  </button>
                ) : (
                  <p className={styles.addressDraft}>Not running — make it live to get an address.</p>
                )}
                <div className={styles.apiCardActions}>
                  <ButtonLink href={`/studio/${encodeURIComponent(s.name)}`} size="sm" variant="secondary">
                    Open
                  </ButtonLink>
                  {isLive ? (
                    <Button size="sm" variant="ghost" icon="stop" onClick={() => stop(s.name)} disabled={pending}>
                      Stop
                    </Button>
                  ) : (
                    <Button size="sm" variant="primary" icon="play" onClick={() => makeLive(s.name)} disabled={pending}>
                      Make live
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    icon="trash"
                    className={styles.pushRight}
                    onClick={() => remove(s.name)}
                    disabled={pending}
                    aria-label={`Delete ${s.name}`}
                    title="Delete"
                  />
                </div>
              </article>
            );
          })}
        </div>
      )}

      {liveWithoutDesign.length > 0 && (
        <section className={styles.orphans}>
          <h2>Running without a saved design</h2>
          <p className={styles.muted}>
            These APIs answer requests but have no saved design here (for example started from the
            command line).
          </p>
          <ul>
            {liveWithoutDesign.map((m) => (
              <li key={m.name}>
                <Badge tone="success" dot>
                  {m.name}
                </Badge>
                <Button size="sm" variant="ghost" icon="stop" onClick={() => stop(m.name)} disabled={pending}>
                  Stop
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
