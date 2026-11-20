"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { Icon } from "@/components/ui/Icon";
import { useToast } from "@/components/ui/feedback";
import { Banner, Button, ButtonLink, Card, CardBody, CardHeader, EmptyState } from "@/components/ui/primitives";
import { createApiKey, getApiBase, listActiveApis, loadSpec } from "@/lib/api";
import { copyText } from "@/lib/copy";
import { curlSnippet, endpointUrl, pandasSnippet, pythonSnippet } from "@/lib/snippets";
import type { ApiSpecDraft } from "@/lib/types";
import styles from "./pages.module.css";

const LANGS = [
  { id: "curl", label: "curl", make: curlSnippet },
  { id: "python", label: "Python", make: pythonSnippet },
  { id: "pandas", label: "pandas", make: pandasSnippet },
] as const;
type Lang = (typeof LANGS)[number]["id"];

/** After publishing: the live address, a key and copy-paste code — no API knowledge needed. */
export function UseYourApi({ name, refreshKey = 0 }: { name: string; refreshKey?: number }) {
  const [spec, setSpec] = useState<ApiSpecDraft | null>(null);
  const [live, setLive] = useState(false);
  const [endpointName, setEndpointName] = useState<string>("");
  const [lang, setLang] = useState<Lang>("curl");
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [loaded, active] = await Promise.all([loadSpec(name), listActiveApis()]);
        if (cancelled) return;
        setSpec(loaded.spec);
        setLive(active.apis.some((a) => a.name === name));
        setEndpointName((cur) => cur || loaded.spec.endpoints[0]?.name || "");
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load API");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [name, refreshKey]);

  const endpoint = spec?.endpoints.find((e) => e.name === endpointName) ?? spec?.endpoints[0];
  const input = useMemo(
    () =>
      spec && endpoint
        ? {
            apiBase: getApiBase(),
            mount: `/apis/${encodeURIComponent(name)}`,
            apiPrefix: spec.app.api_prefix ?? "",
            path: endpoint.path,
            auth: spec.app.auth,
            apiKey: apiKey ?? undefined,
          }
        : null,
    [spec, endpoint, name, apiKey],
  );

  function onCreateKey() {
    startTransition(async () => {
      try {
        const created = await createApiKey(`${name}-key`);
        setApiKey(created.key);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not create a key");
      }
    });
  }

  if (!spec) return error ? <Banner tone="danger">{error}</Banner> : <div className={styles.skeleton} />;

  const snippet = input ? LANGS.find((l) => l.id === lang)!.make(input) : "";
  const url = input ? endpointUrl(input) : "";

  return (
    <Card data-testid="use-your-api" aria-labelledby="use-your-api-title">
      <CardHeader
        id="use-your-api-title"
        icon="zap"
        title="Use your API"
        description={live ? "Copy the code below into a terminal, a script or a notebook." : undefined}
        actions={
          live && (
            <ButtonLink
              size="sm"
              variant="secondary"
              icon="book"
              external
              href={`${getApiBase()}/apis/${encodeURIComponent(name)}/docs`}
            >
              Interactive docs
            </ButtonLink>
          )
        }
      />
      <CardBody className={styles.useStack}>
        {!live ? (
          <EmptyState icon="play" title="Not running yet">
            Make this API live to get its address and ready-to-run code.
          </EmptyState>
        ) : (
          <>
            {spec.endpoints.length > 1 && (
              <label>
                Endpoint
                <select value={endpoint?.name} onChange={(e) => setEndpointName(e.target.value)}>
                  {spec.endpoints.map((e) => (
                    <option key={e.name} value={e.name}>
                      {e.name} — {e.path}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {input && (
              <div>
                <span className={styles.reviewLabel}>Live address</span>
                <button
                  type="button"
                  className={styles.address}
                  onClick={async () => toast((await copyText(url)) ? "Address copied." : "Could not copy.")}
                  title="Copy address"
                >
                  <code data-testid="use-your-api-url">{url}</code>
                  <Icon name="copy" size={14} />
                </button>
              </div>
            )}

            {spec.app.auth === "api_key" &&
              (apiKey ? (
                <Banner tone="warning" role="status">
                  Your new key — shown only once, store it safely:{" "}
                  <code data-testid="use-your-api-key">{apiKey}</code>
                </Banner>
              ) : (
                <div className={styles.keyRow}>
                  <span className={styles.muted}>
                    <Icon name="key" size={14} /> Callers need a key. Create one and it is put into
                    the code for you.
                  </span>
                  <Button size="sm" variant="primary" icon="key" onClick={onCreateKey} busy={pending} disabled={pending}>
                    Create an API key for this code
                  </Button>
                </div>
              ))}
            {spec.app.auth === "jwt" && (
              <Banner tone="accent" role="note">
                This API needs a login token (JWT) from your identity provider. For a quick test, the
                “Try it” tab under Endpoints creates one for you.
              </Banner>
            )}

            <CodeBlock
              code={snippet}
              tabs={LANGS.map(({ id, label }) => ({ id, label }))}
              tab={lang}
              onTab={setLang}
              data-testid="use-your-api-snippet"
            />
          </>
        )}
        {error && <Banner tone="danger">{error}</Banner>}
      </CardBody>
    </Card>
  );
}
