"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, useTransition } from "react";
import { diffSavedSpecs, listSpecs } from "@/lib/api";
import type { OpenApiDiff, SpecListItem } from "@/lib/types";
import styles from "@/components/studio/flow.module.css";

function DiffInner() {
  const search = useSearchParams();
  const [specs, setSpecs] = useState<SpecListItem[]>([]);
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState(search.get("after") ?? "");
  const [result, setResult] = useState<OpenApiDiff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    listSpecs()
      .then((r) => {
        setSpecs(r.specs);
        const qAfter = search.get("after");
        if (r.specs[0]) setBefore(r.specs[0].name);
        if (qAfter && r.specs.some((s) => s.name === qAfter)) setAfter(qAfter);
        else if (r.specs[1]) setAfter(r.specs[1].name);
        else if (r.specs[0]) setAfter(r.specs[0].name);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
  }, [search]);

  function onDiff() {
    setError(null);
    if (!before || !after) {
      setError("Select two specs to compare.");
      return;
    }
    if (before === after) {
      setError("Pick two different specs for a meaningful diff.");
      return;
    }
    startTransition(async () => {
      try {
        const diff = await diffSavedSpecs(before, after);
        setResult(diff);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Diff failed");
      }
    });
  }

  return (
    <>
      <section className={styles.heroBlock}>
        <p className={styles.kicker}>Contract compare</p>
        <h1 className={styles.title}>Diff APIs</h1>
        <p className={styles.lede}>
          Compare OpenAPI surfaces of two saved specs. Breaking path/method removals are flagged.
        </p>
      </section>

      {error && (
        <div className={styles.bannerErr} role="alert">
          {error}
        </div>
      )}

      {specs.length === 0 && !error ? (
        <div className={styles.empty}>No saved specs yet — create one in the wizard first.</div>
      ) : null}

      <div className={styles.diffGrid}>
        <label className={styles.field}>
          Before
          <select value={before} onChange={(e) => setBefore(e.target.value)}>
            {specs.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name} ({s.endpoint_count ?? 0} ep)
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          After
          <select value={after} onChange={(e) => setAfter(e.target.value)}>
            {specs.map((s) => (
              <option key={`a-${s.name}`} value={s.name}>
                {s.name} ({s.endpoint_count ?? 0} ep)
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className={styles.toolbar}>
        <button
          type="button"
          className={styles.primary}
          onClick={onDiff}
          disabled={pending || !before || !after || specs.length === 0}
        >
          Run OpenAPI diff
        </button>
      </div>

      {result && (
        <section className={styles.panel}>
          <h2>{result.breaking ? "Breaking changes detected" : "Compatible changes"}</h2>
          <p>
            +{result.summary.added} / ~{result.summary.updated} / −{result.summary.removed}
          </p>
          <div className={styles.diffOut}>
            {result.changes.length === 0 ? (
              <p>No path/method differences.</p>
            ) : (
              result.changes.map((c, i) => {
                const color =
                  c.type === "NEW" ? styles.diffNew : c.type === "DELETE" ? styles.diffDel : styles.diffUpd;
                const mark = c.type === "NEW" ? "+" : c.type === "DELETE" ? "−" : "~";
                const fields = [
                  c.added_fields?.length ? `+fields ${c.added_fields.join(",")}` : "",
                  c.removed_fields?.length ? `−fields ${c.removed_fields.join(",")}` : "",
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <div key={i} className={color}>
                    <code>
                      {mark} {c.method} {c.path}
                      {c.breaking ? <span className={styles.diffBreak}> BREAKING</span> : null}
                      {fields ? ` (${fields})` : ""}
                    </code>
                  </div>
                );
              })
            )}
          </div>
        </section>
      )}
    </>
  );
}

export default function DiffPage() {
  return (
    <Suspense fallback={<p className={styles.lede}>Loading diff…</p>}>
      <DiffInner />
    </Suspense>
  );
}
