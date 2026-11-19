"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState, useTransition } from "react";
import { StudioShell } from "@/components/studio/StudioShell";
import { UseYourApi } from "@/components/studio/UseYourApi";
import { activateSpec, deactivateSpec, deleteSpec, listActiveApis, loadSpec } from "@/lib/api";
import { LIVE_CHANGED_EVENT } from "@/lib/events";
import styles from "@/components/studio/flow.module.css";

function ApiDetail() {
  const params = useParams<{ name: string }>();
  const search = useSearchParams();
  const name = decodeURIComponent(params.name);
  const [ready, setReady] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(
    search.get("published")
      ? "🎉 Your API is live. Its address, a key and ready-to-run code are below."
      : search.get("saved")
        ? "Saved as a draft. Press “Make live” when you want it to answer requests."
        : null,
  );
  const [pending, startTransition] = useTransition();
  const [liveTick, setLiveTick] = useState(0);

  const refreshLive = useCallback(async () => {
    try {
      const active = await listActiveApis();
      setIsLive(active.apis.some((a) => a.name === name));
    } catch {
      /* status badge is best-effort */
    }
    setLiveTick((t) => t + 1);
  }, [name]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadSpec(name);
        if (!cancelled) setLoadError(null);
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "API not found");
      }
      if (!cancelled) {
        setReady(true);
        await refreshLive();
      }
    })();
    const onLiveChanged = () => void refreshLive();
    window.addEventListener(LIVE_CHANGED_EVENT, onLiveChanged);
    return () => {
      cancelled = true;
      window.removeEventListener(LIVE_CHANGED_EVENT, onLiveChanged);
    };
  }, [name, refreshLive]);

  function run(action: () => Promise<void>, ok: string) {
    setError(null);
    startTransition(async () => {
      try {
        await action();
        setMessage(ok);
        await refreshLive();
      } catch (e) {
        setMessage(null);
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
    });
  }

  const onMakeLive = () =>
    run(async () => {
      const loaded = await loadSpec(name);
      await activateSpec(loaded.spec, name);
    }, "Your API is live (saved version).");

  const onStop = () => {
    if (!window.confirm(`Stop '${name}'? Callers will get an error until you make it live again.`)) return;
    run(() => deactivateSpec(name).then(() => undefined), `'${name}' stopped. Other APIs keep running.`);
  };

  const onDelete = () => {
    if (!window.confirm(`Delete '${name}'? It is stopped and its saved design removed.`)) return;
    setError(null);
    startTransition(async () => {
      try {
        if (isLive) await deactivateSpec(name);
        await deleteSpec(name);
        window.location.assign("/studio");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Delete failed.");
      }
    });
  };

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
          ← My APIs
        </Link>
      </section>
    );
  }

  return (
    <>
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>API</p>
        <h1 className={styles.title}>
          {name}{" "}
          <span className={isLive ? styles.badgeLive : styles.badge} data-testid="api-status">
            {isLive ? "Live" : "Draft — not running"}
          </span>
        </h1>
        <p className={styles.lede}>
          Change anything in the editor below, then press <strong>Save &amp; make live</strong> to
          update the running API.
        </p>
        <div className={styles.toolbar}>
          <Link className={styles.ghost} href="/studio">
            ← My APIs
          </Link>
          {isLive ? (
            <button type="button" className={styles.secondary} onClick={onStop} disabled={pending}>
              Stop
            </button>
          ) : (
            <button type="button" className={styles.primary} onClick={onMakeLive} disabled={pending}>
              Make live
            </button>
          )}
          <Link className={styles.secondary} href={`/studio/diff?after=${encodeURIComponent(name)}`}>
            Compare versions
          </Link>
          <button type="button" className={styles.danger} onClick={onDelete} disabled={pending}>
            Delete
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

      <UseYourApi name={name} refreshKey={liveTick} />

      <div className={styles.wideShell}>
        <StudioShell initialName={name} embedded />
      </div>
    </>
  );
}

export default function ApiDetailPage() {
  return (
    <Suspense>
      <ApiDetail />
    </Suspense>
  );
}
