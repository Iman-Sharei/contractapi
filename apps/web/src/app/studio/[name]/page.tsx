"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { StudioShell } from "@/components/studio/StudioShell";
import {
  activateSpec,
  deactivateSpec,
  deleteSpec,
  getActive,
  getApiBase,
  loadSpec,
} from "@/lib/api";
import styles from "@/components/studio/flow.module.css";

export default function ApiDetailPage() {
  const params = useParams<{ name: string }>();
  const router = useRouter();
  const name = decodeURIComponent(params.name);
  const [ready, setReady] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadSpec(name);
        if (cancelled) return;
        setReady(true);
        setLoadError(null);
      } catch (e) {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : "Spec not found");
        setReady(true);
      }
      try {
        const a = await getActive();
        if (!cancelled) setIsLive(Boolean(a.active && a.name === name));
      } catch {
        /* ignore live badge */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [name]);

  function setOk(msg: string) {
    setMessage(msg);
    setError(null);
  }
  function setErr(msg: string) {
    setError(msg);
    setMessage(null);
  }

  function onActivate() {
    startTransition(async () => {
      try {
        const loaded = await loadSpec(name);
        await activateSpec(loaded.spec, name);
        setIsLive(true);
        setOk(`Activated → ${getApiBase()}/data/docs`);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Activate failed");
      }
    });
  }

  function onDeactivate() {
    startTransition(async () => {
      try {
        await deactivateSpec();
        setIsLive(false);
        setOk("Deactivated.");
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Deactivate failed");
      }
    });
  }

  function onDelete() {
    if (!window.confirm(`Delete '${name}'?`)) return;
    startTransition(async () => {
      try {
        await deleteSpec(name);
        router.push("/studio");
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Delete failed");
      }
    });
  }

  if (!ready) {
    return (
      <div className={styles.empty} aria-busy="true">
        Loading {name}…
      </div>
    );
  }

  if (loadError) {
    return (
      <section className={styles.panel} role="alert">
        <h1 className={styles.title}>Not found</h1>
        <p>{loadError}</p>
        <Link className={styles.secondary} href="/studio">
          ← Catalog
        </Link>
      </section>
    );
  }

  return (
    <>
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>API detail</p>
        <h1 className={styles.title}>{name}</h1>
        <p className={styles.lede}>
          Edit the contract in the editor below. Use Save inside the shell, then Activate when ready.
        </p>
        <div className={styles.toolbar}>
          <Link className={styles.ghost} href="/studio">
            ← Catalog
          </Link>
          <button type="button" className={styles.primary} onClick={onActivate} disabled={pending}>
            Activate saved
          </button>
          {isLive && (
            <button type="button" className={styles.secondary} onClick={onDeactivate} disabled={pending}>
              Deactivate
            </button>
          )}
          <Link className={styles.secondary} href={`/studio/diff?after=${encodeURIComponent(name)}`}>
            Diff
          </Link>
          <button type="button" className={styles.danger} onClick={onDelete} disabled={pending}>
            Delete
          </button>
          {isLive && <span className={styles.badgeLive}>live</span>}
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

      <div className={styles.wideShell}>
        <StudioShell initialName={name} embedded />
      </div>
    </>
  );
}
