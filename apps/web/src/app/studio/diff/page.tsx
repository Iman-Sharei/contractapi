"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, useTransition } from "react";
import { diffSavedSpecs, listSpecs } from "@/lib/api";
import type { OpenApiDiff, SpecListItem } from "@/lib/types";
import { Icon } from "@/components/ui/Icon";
import { Badge, Banner, Button, Card, CardBody, CardHeader, EmptyState, Method, PageHeader, cx } from "@/components/ui/primitives";
import styles from "@/components/studio/pages.module.css";

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
      <PageHeader
        eyebrow="Studio"
        title="Compare versions"
        description="Pick two saved APIs to see what changed. Changes that would break existing callers (a removed address or operation) are flagged."
      />

      {error && (
        <Banner tone="danger" className={styles.gapBottom}>
          {error}
        </Banner>
      )}

      {specs.length === 0 && !error ? (
        <EmptyState icon="compare" title="Nothing to compare yet">
          Create an API in the wizard first; every save keeps a version you can compare.
        </EmptyState>
      ) : (
        <Card>
          <CardBody className={styles.diffPicker}>
            <label>
              Before
              <select value={before} onChange={(e) => setBefore(e.target.value)}>
                {specs.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name} ({s.endpoint_count ?? 0} endpoints)
                  </option>
                ))}
              </select>
            </label>
            <span className={styles.diffArrow} aria-hidden>
              <Icon name="arrowRight" />
            </span>
            <label>
              After
              <select value={after} onChange={(e) => setAfter(e.target.value)}>
                {specs.map((s) => (
                  <option key={`a-${s.name}`} value={s.name}>
                    {s.name} ({s.endpoint_count ?? 0} endpoints)
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="primary"
              icon="compare"
              onClick={onDiff}
              busy={pending}
              disabled={pending || !before || !after}
            >
              Compare
            </Button>
          </CardBody>
        </Card>
      )}

      {result && (
        <Card className={styles.diffResult}>
          <CardHeader
            icon={result.breaking ? "alert" : "checkCircle"}
            title={
              result.breaking
                ? "These changes would break existing callers"
                : "Safe changes — existing callers keep working"
            }
            actions={
              <>
                <Badge tone="success">+{result.summary.added} added</Badge>
                <Badge tone="warning">~{result.summary.updated} changed</Badge>
                <Badge tone="danger">−{result.summary.removed} removed</Badge>
              </>
            }
          />
          <CardBody>
            {result.changes.length === 0 ? (
              <p className={styles.muted}>No differences in addresses or operations.</p>
            ) : (
              <ul className={styles.diffList}>
                {result.changes.map((c, i) => {
                  const kind = c.type === "NEW" ? "added" : c.type === "DELETE" ? "removed" : "changed";
                  return (
                    <li key={i} className={cx(styles.diffRow, styles[`diff-${kind}`])}>
                      <span className={styles.diffKind}>{kind}</span>
                      <Method method={c.method} />
                      <code>{c.path}</code>
                      {c.breaking && <Badge tone="danger">Breaking</Badge>}
                      {c.added_fields?.length ? (
                        <span className={styles.muted}>+ fields {c.added_fields.join(", ")}</span>
                      ) : null}
                      {c.removed_fields?.length ? (
                        <span className={styles.muted}>− fields {c.removed_fields.join(", ")}</span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardBody>
        </Card>
      )}
    </>
  );
}

export default function DiffPage() {
  return (
    <Suspense fallback={<p className={styles.muted}>Loading…</p>}>
      <DiffInner />
    </Suspense>
  );
}
