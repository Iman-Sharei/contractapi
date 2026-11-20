"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Icon } from "@/components/ui/Icon";
import { useConfirm, useToast } from "@/components/ui/feedback";
import { Badge, Banner, Button, ButtonLink, EmptyState, PageHeader, Tabs } from "@/components/ui/primitives";
import { loadSpec } from "@/lib/api";
import { useEditorState } from "../editor/useEditorState";
import styles from "../pages.module.css";
import { EndpointsTab } from "./EndpointsTab";
import { FileTab } from "./FileTab";
import { OverviewTab } from "./OverviewTab";
import { SettingsTab } from "./SettingsTab";
import { useLiveStatus } from "./useLiveStatus";

const TABS = ["overview", "endpoints", "settings", "file"] as const;
type Tab = (typeof TABS)[number];

/** One API: status and actions on top, then Overview / Endpoints / Settings / API file. */
export function ApiWorkspace({ name }: { name: string }) {
  const s = useEditorState({ initialName: name, embedded: true });
  const live = useLiveStatus(name);
  const router = useRouter();
  const search = useSearchParams();
  const confirm = useConfirm();
  const toast = useToast();
  const [busy, startTransition] = useTransition();
  const [found, setFound] = useState<boolean | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(
    search.get("published")
      ? "Your API is live. Its address, a key and ready-to-run code are below."
      : search.get("saved")
        ? "Saved as a draft. Press “Make live” when you want it to answer requests."
        : null,
  );

  const raw = search.get("tab");
  const tab: Tab = (TABS as readonly string[]).includes(raw ?? "") ? (raw as Tab) : "overview";
  const setTab = (t: Tab) => {
    const q = new URLSearchParams(search.toString());
    q.delete("published");
    q.delete("saved");
    if (t === "overview") q.delete("tab");
    else q.set("tab", t);
    const qs = q.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  };

  useEffect(() => {
    let cancelled = false;
    loadSpec(name)
      .then(() => !cancelled && setFound(true))
      .catch(() => !cancelled && setFound(false));
    return () => {
      cancelled = true;
    };
  }, [name]);

  // Editor status messages ("Saved…", "Copied…") show as short toasts.
  const { message, setMessage } = s;
  useEffect(() => {
    if (!message) return;
    toast(message);
    setMessage(null);
  }, [message, setMessage, toast]);

  function run(action: () => Promise<void>, ok: string) {
    setActionError(null);
    startTransition(async () => {
      try {
        await action();
        toast(ok);
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Something went wrong.");
      }
    });
  }

  const onMakeLive = () => run(live.makeLive, "Your API is live.");

  async function onStop() {
    const ok = await confirm({
      title: `Stop '${name}'?`,
      body: "Callers get an error until you make it live again. Other APIs keep running.",
      confirmLabel: "Stop API",
    });
    if (ok) run(live.stop, `'${name}' stopped. Other APIs keep running.`);
  }

  async function onDelete() {
    const ok = await confirm({
      title: `Delete '${name}'?`,
      body: "It stops answering requests and its saved design is removed. This can't be undone.",
      confirmLabel: "Delete API",
    });
    if (!ok) return;
    setActionError(null);
    startTransition(async () => {
      try {
        await live.remove();
        window.location.assign("/studio");
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Delete failed.");
      }
    });
  }

  if (found === null) {
    return (
      <div className={styles.loadingPage} aria-busy="true">
        <span className={styles.spinnerLg} aria-hidden /> Loading {name}…
      </div>
    );
  }

  if (!found) {
    return (
      <EmptyState
        icon="search"
        title="API not found"
        action={
          <ButtonLink href="/studio" icon="arrowLeft">
            My APIs
          </ButtonLink>
        }
      >
        There is no saved API called <code>{name}</code>. It may have been deleted.
      </EmptyState>
    );
  }

  const pending = busy || s.pending;
  const error = actionError ?? s.error;
  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <Link href="/studio">My APIs</Link>
            <Icon name="chevronRight" size={12} />
            <span>{name}</span>
          </>
        }
        title={
          <>
            {name}
            <Badge tone={live.isLive ? "success" : "neutral"} dot pulse={live.isLive} data-testid="api-status">
              {live.isLive ? "Live" : "Draft — not running"}
            </Badge>
          </>
        }
        description={s.spec.app.title || undefined}
        actions={
          <>
            {s.dirty ? (
              <>
                <Badge tone="warning" dot>
                  Unsaved changes
                </Badge>
                <Button variant="secondary" onClick={s.onSave} disabled={pending}>
                  Save draft
                </Button>
                <Button variant="primary" icon="zap" onClick={s.onActivate} disabled={pending} busy={pending}>
                  Save &amp; make live
                </Button>
              </>
            ) : live.isLive ? (
              <Button variant="secondary" icon="stop" onClick={onStop} disabled={pending}>
                Stop
              </Button>
            ) : (
              <Button variant="primary" icon="play" onClick={onMakeLive} disabled={pending || !live.known}>
                Make live
              </Button>
            )}
            <ButtonLink variant="ghost" icon="compare" href={`/studio/diff?after=${encodeURIComponent(name)}`}>
              Compare versions
            </ButtonLink>
            <Button variant="ghost" icon="trash" onClick={onDelete} disabled={pending}>
              Delete
            </Button>
          </>
        }
      />

      <div className={styles.workspaceBanners}>
        {notice && (
          <Banner tone="success" onDismiss={() => setNotice(null)}>
            {notice}
          </Banner>
        )}
        {error && (
          <Banner
            tone="danger"
            onDismiss={() => {
              setActionError(null);
              s.setError(null);
            }}
          >
            {error}
          </Banner>
        )}
      </div>

      <Tabs
        label="API sections"
        value={tab}
        onChange={setTab}
        className={styles.workspaceTabs}
        items={[
          { id: "overview", label: "Overview", icon: "grid" },
          { id: "endpoints", label: "Endpoints", icon: "layers", count: s.spec.endpoints.length },
          { id: "settings", label: "Settings", icon: "settings" },
          { id: "file", label: "API file", icon: "file" },
        ]}
      />

      <div className={styles.workspaceBody} aria-busy={pending || undefined}>
        {tab === "overview" && (
          <OverviewTab s={s} name={name} refreshKey={live.tick} onEdit={() => setTab("endpoints")} />
        )}
        {tab === "endpoints" && <EndpointsTab s={s} />}
        {tab === "settings" && <SettingsTab s={s} />}
        {tab === "file" && <FileTab s={s} />}
      </div>
    </>
  );
}
