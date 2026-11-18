"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { formatApiError } from "@/lib/formatError";
import styles from "@/components/studio/flow.module.css";

/** Only same-site relative paths: never redirect off-site after login. */
function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/studio";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState(false);

  useEffect(() => {
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
      router.replace(next);
      router.refresh();
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
        server). It is kept in a secure, browser-only cookie.
      </p>
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
