"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { ActivityCard } from "@/components/studio/ops/ActivityCard";
import { DownloadsCard } from "@/components/studio/ops/DownloadsCard";
import { KeysCard } from "@/components/studio/ops/KeysCard";
import type { RunAction } from "@/components/studio/ops/shared";
import { VersionsCard } from "@/components/studio/ops/VersionsCard";
import { useToast } from "@/components/ui/feedback";
import { Banner, Button, PageHeader, Tabs } from "@/components/ui/primitives";
import { getAudit, listApiKeys, listSpecs } from "@/lib/api";
import type { ApiKeyInfo } from "@/lib/types";
import type { SpecListItem } from "@/lib/types";
import styles from "@/components/studio/pages.module.css";

type Section = "keys" | "versions" | "downloads" | "activity";

export default function OpsPage() {
  const [section, setSection] = useState<Section>("keys");
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [specs, setSpecs] = useState<SpecListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const refresh = useCallback(() => {
    startTransition(async () => {
      try {
        const [k, a, s] = await Promise.all([listApiKeys(), getAudit(80), listSpecs()]);
        setKeys(k.keys);
        setEvents(a.events);
        setSpecs(s.specs);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Load failed");
      }
    });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const run: RunAction = (action, ok) => {
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
  };

  return (
    <>
      <PageHeader
        eyebrow="Studio"
        title="Keys & settings"
        description="Create keys for the people and apps that call your APIs, restore earlier versions, copy an API to staging or production, and download ready-made clients."
        actions={<Button variant="ghost" icon="refresh" onClick={refresh} disabled={pending} aria-label="Refresh" />}
      />

      {error && (
        <Banner tone="danger" className={styles.gapBottom} onDismiss={() => setError(null)}>
          {error}
        </Banner>
      )}

      <Tabs
        label="Settings sections"
        value={section}
        onChange={setSection}
        className={styles.workspaceTabs}
        items={[
          { id: "keys", label: "API keys", icon: "key", count: keys.filter((k) => !k.revoked).length },
          { id: "versions", label: "Versions & environments", icon: "compare" },
          { id: "downloads", label: "Downloads", icon: "file" },
          { id: "activity", label: "Activity", icon: "book" },
        ]}
      />

      {section === "keys" && (
        <KeysCard keys={keys} apiNames={specs.map((x) => x.name)} pending={pending} run={run} />
      )}
      {section === "versions" && <VersionsCard specs={specs} pending={pending} run={run} onError={setError} />}
      {section === "downloads" && <DownloadsCard specs={specs} pending={pending} run={run} />}
      {section === "activity" && <ActivityCard events={events} />}
    </>
  );
}
