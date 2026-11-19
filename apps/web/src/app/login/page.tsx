"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { formatApiError } from "@/lib/formatError";
import styles from "@/components/studio/flow.module.css";

/** Only same-site relative paths: never redirect off-site after login. */
function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/studio";
}

function LoginForm() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState(false);
  const [demoKey, setDemoKey] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/session", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => setDemoKey(typeof s?.demoKey === "string" ? s.demoKey : null))
      .catch(() => setDemoKey(null));
    fetch("/api/studio/oidc/config", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg) => setSso(Boolean(cfg?.browser_login)))
      .catch(() => setSso(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    setBusy(false);
    if (res.ok) {
      // Full navigation: the client router may hold a "redirect to /login" cached from a link
      // prefetched while signed out, which would bounce the user straight back here.
      window.location.assign(next);
      return;
    }
    const body = await res.json().catch(() => null);
    setError(formatApiError(body, res.status, res.statusText));
  }

  return (
    <main className={styles.page} style={{ maxWidth: 440 }}>
      <h1 className={styles.title}>Sign in to Studio</h1>
      <p className={styles.lede}>
        Paste the Studio key your administrator gave you (the <code>STUDIO_API_KEY</code> of the
        server). The key is only checked here — your browser keeps a signed sign-in that expires
        after 12 hours, never the key itself.
      </p>
      {demoKey ? (
        <div className={styles.bannerOk} role="note" data-testid="login-demo-hint">
          <span>
            This is a demo install, so the key is <code>{demoKey}</code>.{" "}
            <button type="button" className={styles.ghost} onClick={() => setKey(demoKey)}>
              Use it
            </button>
            <br />
            Before real use, set your own <code>STUDIO_API_KEY</code> in the server&apos;s{" "}
            <code>.env</code> file and restart.
          </span>
        </div>
      ) : (
        <p className={styles.hint} data-testid="login-key-hint">
          Don&apos;t have it? Ask whoever runs this server. They can read it with{" "}
          <code>docker compose exec web printenv STUDIO_API_KEY</code>.
        </p>
      )}
      <form onSubmit={submit} className={styles.panel} style={{ display: "grid", gap: 12 }}>
        <label className={styles.field}>
          Studio key
          <input
            type="password"
            autoComplete="current-password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            data-testid="login-key"
            required
          />
        </label>
        {error && (
          <p className={styles.bannerErr} role="alert">
            {error}
          </p>
        )}
        <button type="submit" className={styles.primary} disabled={busy} data-testid="login-submit">
          {busy ? "Checking…" : "Sign in"}
        </button>
        {sso && (
          <a
            className={styles.secondary}
            href={`/api/studio/oidc/login?return_to=${encodeURIComponent(next)}`}
          >
            Sign in with SSO
          </a>
        )}
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
