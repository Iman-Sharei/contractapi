"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { createApiKey, getApiBase, listActiveApis, loadSpec } from "@/lib/api";
import { copyText } from "@/lib/copy";
import { curlSnippet, endpointUrl, pandasSnippet, pythonSnippet } from "@/lib/snippets";
import type { ApiSpecDraft } from "@/lib/types";
import { SafetyChecklist } from "./SafetyChecklist";
import styles from "./flow.module.css";

const LANGS = [
  ["curl", "curl", curlSnippet],
  ["python", "Python", pythonSnippet],
  ["pandas", "pandas", pandasSnippet],
] as const;

/** After activation: the live URL, a key, and copy-paste code — no API knowledge needed. */
export function UseYourApi({ name, refreshKey = 0 }: { name: string; refreshKey?: number }) {
  const [spec, setSpec] = useState<ApiSpecDraft | null>(null);
  const [live, setLive] = useState(false);
  const [endpointName, setEndpointName] = useState<string>("");
  const [lang, setLang] = useState<(typeof LANGS)[number][0]>("curl");
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

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

  if (!spec) return error ? <p className={styles.bannerErr}>{error}</p> : null;

  const snippet = input ? LANGS.find(([id]) => id === lang)![2](input) : "";

  return (
    <section className={styles.panel} data-testid="use-your-api" aria-labelledby="use-your-api-title">
      <h2 id="use-your-api-title">Use your API</h2>
      {!live ? (
        <p className={styles.hint}>Make this API live to get its address and ready-to-run code.</p>
      ) : (
        <>
          {spec.endpoints.length > 1 && (
            <label className={styles.field}>
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
            <p>
              Live URL: <code data-testid="use-your-api-url">{endpointUrl(input)}</code>
            </p>
          )}

          {spec.app.auth === "api_key" && (
            <div className={styles.toolbar}>
              {apiKey ? (
                <p className={styles.revealBox} role="status">
                  Your new key (shown only once — store it safely): <code data-testid="use-your-api-key">{apiKey}</code>
                </p>
              ) : (
                <button type="button" className={styles.secondary} onClick={onCreateKey} disabled={pending}>
                  Create an API key for this code
                </button>
              )}
            </div>
          )}
          {spec.app.auth === "jwt" && (
            <p className={styles.hint}>
              This API needs a login token (JWT) from your identity provider. For a quick test, the Play tab
              below creates one for you.
            </p>
          )}

          <div className={styles.chipRow} role="tablist" aria-label="Language">
            {LANGS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={lang === id}
                className={lang === id ? styles.chipOn : styles.chip}
                onClick={() => setLang(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <pre data-testid="use-your-api-snippet">
            <code>{snippet}</code>
          </pre>
          <div className={styles.toolbar}>
            <button
              type="button"
              className={styles.secondary}
              onClick={async () => setCopied(await copyText(snippet))}
            >
              {copied ? "Copied" : "Copy code"}
            </button>
            <a
              className={styles.ghost}
              href={`${getApiBase()}/apis/${encodeURIComponent(name)}/docs`}
              target="_blank"
              rel="noreferrer"
            >
              Interactive docs
            </a>
          </div>
        </>
      )}

      <SafetyChecklist spec={spec} title="Before you share it" />
      {error && <p className={styles.bannerErr}>{error}</p>}
    </section>
  );
}
