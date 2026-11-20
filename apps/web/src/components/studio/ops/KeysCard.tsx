"use client";

import { useState } from "react";
import { useConfirm } from "@/components/ui/feedback";
import { Badge, Banner, Button, Card, CardBody, CardHeader, EmptyState, Hint } from "@/components/ui/primitives";
import { createApiKey, revokeApiKey } from "@/lib/api";
import { copyText } from "@/lib/copy";
import styles from "../pages.module.css";
import type { RunAction } from "./shared";

export type KeyRow = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  revoked: boolean;
};

export function KeysCard({ keys, pending, run }: { keys: KeyRow[]; pending: boolean; run: RunAction }) {
  const [name, setName] = useState("studio");
  const [scopes, setScopes] = useState("*");
  const [revealed, setRevealed] = useState<string | null>(null);
  const [showRevoked, setShowRevoked] = useState(false);
  const confirm = useConfirm();

  function create(e: React.FormEvent) {
    e.preventDefault();
    run(async () => {
      const list = scopes
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const created = await createApiKey(name, list.length ? list : ["*"]);
      setRevealed(created.key);
    }, "Key created — copy it now, it won't be shown again.");
  }

  async function revoke(k: KeyRow) {
    const ok = await confirm({
      title: `Revoke key '${k.name}'?`,
      body: `Apps using ${k.prefix}… stop working immediately. This can't be undone.`,
      confirmLabel: "Revoke key",
    });
    if (ok) run(() => revokeApiKey(k.id), "Key revoked.");
  }

  const visible = keys.filter((k) => showRevoked || !k.revoked);
  const revokedCount = keys.filter((k) => k.revoked).length;

  return (
    <Card>
      <CardHeader
        icon="key"
        title="API keys"
        description="Give each app or person its own key, so you can revoke one without breaking the others."
      />
      <CardBody className={styles.useStack}>
        <form className={styles.keyForm} onSubmit={create}>
          <label>
            Who is this key for?
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. sales-dashboard" required />
          </label>
          <label>
            Permissions
            <input value={scopes} onChange={(e) => setScopes(e.target.value)} placeholder="* or read,write" />
            <Hint>
              <code>*</code> = everything, or a list like <code>read,write</code>.
            </Hint>
          </label>
          <Button type="submit" variant="primary" icon="plus" disabled={pending}>
            Create key
          </Button>
        </form>

        {revealed && (
          <Banner tone="warning" role="status" onDismiss={() => setRevealed(null)}>
            <p>
              <strong>Copy this key now</strong> — for your safety it is shown only once.
            </p>
            <div className={styles.secretRow}>
              <code>{revealed}</code>
              <Button
                size="sm"
                variant="secondary"
                icon="copy"
                onClick={async () => {
                  if (await copyText(revealed)) setRevealed(null);
                }}
              >
                Copy &amp; hide
              </Button>
            </div>
          </Banner>
        )}

        {visible.length === 0 ? (
          <EmptyState icon="key" title="No keys yet">
            Create one above and give it to the app or person that calls your API.
          </EmptyState>
        ) : (
          <ul className={styles.keyList}>
            {visible.map((k) => (
              <li key={k.id} className={k.revoked ? styles.keyRevoked : undefined}>
                <div className={styles.keyInfo}>
                  <strong>{k.name}</strong>
                  <span className={styles.muted}>
                    <code>{k.prefix}…</code> · {(k.scopes || []).join(", ") || "*"}
                  </span>
                </div>
                {k.revoked ? (
                  <Badge>Revoked</Badge>
                ) : (
                  <Button size="sm" variant="danger" onClick={() => revoke(k)} disabled={pending}>
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {revokedCount > 0 && (
          <div>
            <Button size="sm" variant="ghost" onClick={() => setShowRevoked((v) => !v)}>
              {showRevoked ? "Hide" : "Show"} {revokedCount} revoked key{revokedCount === 1 ? "" : "s"}
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
