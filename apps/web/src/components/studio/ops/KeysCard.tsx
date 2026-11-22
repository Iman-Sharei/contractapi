"use client";

import { useState } from "react";
import { useConfirm } from "@/components/ui/feedback";
import { Badge, Banner, Button, Card, CardBody, CardHeader, EmptyState, Hint } from "@/components/ui/primitives";
import { createApiKey, revokeApiKey } from "@/lib/api";
import { copyText } from "@/lib/copy";
import { keyAccess, keyApis, keyLastUsed, keyStatus } from "@/lib/keys";
import type { ApiKeyInfo } from "@/lib/types";
import styles from "../pages.module.css";
import type { RunAction } from "./shared";

const EXPIRY = [
  { label: "Never", days: null },
  { label: "In 30 days", days: 30 },
  { label: "In 90 days", days: 90 },
  { label: "In 1 year", days: 365 },
] as const;

/** Keys open only the APIs and access they are created for, so one leaked key exposes little. */
export function KeysCard({
  keys,
  apiNames,
  pending,
  run,
}: {
  keys: ApiKeyInfo[];
  apiNames: string[];
  pending: boolean;
  run: RunAction;
}) {
  const [name, setName] = useState("");
  const [apis, setApis] = useState<string[]>([]);
  const [allApis, setAllApis] = useState(false);
  const [access, setAccess] = useState<"read" | "write">("read");
  const [expiresInDays, setExpiresInDays] = useState<number | null>(90);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [showRevoked, setShowRevoked] = useState(false);
  const confirm = useConfirm();

  const chosen = allApis ? ["*"] : apis;

  function create(e: React.FormEvent) {
    e.preventDefault();
    run(async () => {
      const created = await createApiKey(name.trim(), { apis: chosen, access, expiresInDays });
      setRevealed(created.key);
      setName("");
    }, "Key created — copy it now, it won't be shown again.");
  }

  async function revoke(k: ApiKeyInfo) {
    const ok = await confirm({
      title: `Revoke key '${k.name}'?`,
      body: `Apps using ${k.prefix}… stop working immediately. This can't be undone.`,
      confirmLabel: "Revoke key",
    });
    if (ok) run(() => revokeApiKey(k.id), "Key revoked.");
  }

  const toggleApi = (api: string) =>
    setApis((cur) => (cur.includes(api) ? cur.filter((a) => a !== api) : [...cur, api]));
  const visible = keys.filter((k) => showRevoked || !k.revoked);
  const revokedCount = keys.filter((k) => k.revoked).length;

  return (
    <Card>
      <CardHeader
        icon="key"
        title="API keys"
        description="Give each app or person its own key, for only the APIs it needs. Revoke one without breaking the others."
      />
      <CardBody className={styles.useStack}>
        <form className={styles.keyFormGrid} onSubmit={create} data-testid="key-form">
          <label>
            Who is this key for?
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. sales-dashboard" required />
          </label>
          <fieldset className={styles.keyApis}>
            <legend>Which APIs may it call?</legend>
            {apiNames.map((api) => (
              <label key={api}>
                <input
                  type="checkbox"
                  checked={allApis || apis.includes(api)}
                  disabled={allApis}
                  onChange={() => toggleApi(api)}
                  data-testid={`key-api-${api}`}
                />
                {api}
              </label>
            ))}
            <label>
              <input type="checkbox" checked={allApis} onChange={(e) => setAllApis(e.target.checked)} data-testid="key-all-apis" />
              All APIs, also future ones
            </label>
            {allApis && <Hint className={styles.hintWarn}>A leaked key would open every API. Prefer one key per API.</Hint>}
          </fieldset>
          <fieldset className={styles.keyApis}>
            <legend>What may it do?</legend>
            <label>
              <input type="radio" name="key-access" checked={access === "read"} onChange={() => setAccess("read")} />
              Read data
            </label>
            <label>
              <input
                type="radio"
                name="key-access"
                checked={access === "write"}
                onChange={() => setAccess("write")}
                data-testid="key-access-write"
              />
              Read and change data
            </label>
            <Hint>Changing is only possible on APIs that allow it.</Hint>
          </fieldset>
          <label>
            Stops working
            <select
              value={expiresInDays ?? ""}
              onChange={(e) => setExpiresInDays(e.target.value ? Number(e.target.value) : null)}
            >
              {EXPIRY.map((x) => (
                <option key={x.label} value={x.days ?? ""}>
                  {x.label}
                </option>
              ))}
            </select>
          </label>
          <div>
            <Button type="submit" variant="primary" icon="plus" disabled={pending || !name.trim() || chosen.length === 0}>
              Create key
            </Button>
            {chosen.length === 0 && <Hint>Choose at least one API.</Hint>}
          </div>
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
          <ul className={styles.keyList} data-testid="key-list">
            {visible.map((k) => {
              const status = keyStatus(k);
              const everyApi = k.apis.includes("*");
              return (
                <li key={k.id} className={k.revoked ? styles.keyRevoked : undefined}>
                  <div className={styles.keyInfo}>
                    <strong>{k.name}</strong>
                    <span className={styles.muted}>
                      <code>{k.prefix}…</code> · {keyApis(k)} · {keyAccess(k)} · {keyLastUsed(k)}
                    </span>
                    {everyApi && !k.revoked && (
                      <Hint className={styles.hintWarn}>
                        Works on every API. Replace it with a key for the APIs it needs.
                      </Hint>
                    )}
                  </div>
                  <Badge tone={status === "Active" ? "success" : status.startsWith("Expires") ? "warning" : "neutral"}>
                    {status}
                  </Badge>
                  {!k.revoked && (
                    <Button size="sm" variant="danger" onClick={() => revoke(k)} disabled={pending}>
                      Revoke
                    </Button>
                  )}
                </li>
              );
            })}
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
