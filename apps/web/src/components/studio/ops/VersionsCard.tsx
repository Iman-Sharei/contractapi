"use client";

import { useEffect, useState, useTransition } from "react";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { useConfirm } from "@/components/ui/feedback";
import { Button, Card, CardBody, CardHeader, EmptyState, ui } from "@/components/ui/primitives";
import { getSnapshot, listHistory, promoteSpec, restoreSnapshot } from "@/lib/api";
import type { SpecListItem } from "@/lib/types";
import styles from "../pages.module.css";
import type { RunAction } from "./shared";

export function VersionsCard({
  specs,
  pending,
  run,
  onError,
}: {
  specs: SpecListItem[];
  pending: boolean;
  run: RunAction;
  onError: (msg: string) => void;
}) {
  const [promoteName, setPromoteName] = useState("");
  const [env, setEnv] = useState("staging");
  const [historyName, setHistoryName] = useState("");
  const [snapshots, setSnapshots] = useState<{ id: string; path: string }[]>([]);
  const [preview, setPreview] = useState<{ id: string; yaml: string } | null>(null);
  const [loading, startTransition] = useTransition();
  const confirm = useConfirm();

  useEffect(() => {
    if (!promoteName && specs[0]) setPromoteName(specs[0].name);
    if (!historyName && specs[0]) setHistoryName(specs[0].name);
  }, [specs, promoteName, historyName]);

  useEffect(() => {
    if (!historyName) return;
    setPreview(null);
    startTransition(async () => {
      try {
        setSnapshots((await listHistory(historyName)).snapshots);
      } catch {
        setSnapshots([]);
      }
    });
  }, [historyName]);

  async function promote() {
    const target = `${promoteName}_${env}`;
    const ok = await confirm({
      title: `Copy '${promoteName}' to ${env}?`,
      body: `A copy named '${target}' is saved and marked for ${env}. The original is not changed.`,
      confirmLabel: "Copy it",
      tone: "primary",
    });
    if (ok) run(() => promoteSpec(promoteName, env), `Saved a copy as '${target}'.`);
  }

  async function restore(id: string) {
    const ok = await confirm({
      title: `Restore '${historyName}' to this version?`,
      body: "The current design is kept in the history first, so you can come back to it.",
      confirmLabel: "Restore",
      tone: "primary",
    });
    if (ok) run(() => restoreSnapshot(historyName, id), `Restored '${historyName}'. Make it live from its page.`);
  }

  if (specs.length === 0) {
    return (
      <EmptyState icon="compare" title="No saved APIs yet">
        Versions appear here after you save an API.
      </EmptyState>
    );
  }

  return (
    <div className={styles.settingsStack}>
      <Card>
        <CardHeader
          icon="layers"
          title="Copy to another environment"
          description={
            <>
              Saves a copy named <code>{promoteName || "name"}_{env}</code>, marked for that environment.
            </>
          }
        />
        <CardBody className={styles.inlineForm}>
          <label>
            API
            <select value={promoteName} onChange={(e) => setPromoteName(e.target.value)}>
              {specs.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Environment
            <select value={env} onChange={(e) => setEnv(e.target.value)}>
              <option value="staging">staging</option>
              <option value="production">production</option>
              <option value="development">development</option>
            </select>
          </label>
          <Button variant="primary" icon="arrowRight" onClick={promote} disabled={pending || !promoteName}>
            Copy
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          icon="refresh"
          title="Restore an earlier version"
          description="Every save keeps the previous version. Preview one before restoring it."
        />
        <CardBody className={ui.stack}>
          <label className={styles.narrowField}>
            API
            <select value={historyName} onChange={(e) => setHistoryName(e.target.value)}>
              {specs.map((s) => (
                <option key={`h-${s.name}`} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {snapshots.length === 0 ? (
            <p className={styles.muted}>
              {loading ? "Loading…" : "No earlier versions yet — every save keeps the previous one here."}
            </p>
          ) : (
            <ul className={styles.keyList}>
              {snapshots.map((snap) => (
                <li key={snap.id}>
                  <code>{snap.id}</code>
                  <span className={ui.row}>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        startTransition(async () => {
                          try {
                            const data = await getSnapshot(historyName, snap.id);
                            setPreview({ id: snap.id, yaml: data.yaml });
                          } catch (e) {
                            onError(e instanceof Error ? e.message : "Preview failed");
                          }
                        })
                      }
                    >
                      Preview
                    </Button>
                    <Button size="sm" variant="primary" onClick={() => restore(snap.id)} disabled={pending}>
                      Restore
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {preview && (
            <div className={ui.stack}>
              <div className={ui.row}>
                <strong>Version {preview.id}</strong>
                <Button size="sm" variant="ghost" icon="x" onClick={() => setPreview(null)}>
                  Close
                </Button>
              </div>
              <CodeBlock code={preview.yaml} title="contract.yaml" />
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
