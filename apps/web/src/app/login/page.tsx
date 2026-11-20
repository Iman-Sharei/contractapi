"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { formatApiError } from "@/lib/formatError";
import { Brand } from "@/components/studio/StudioFrame";
import { Icon } from "@/components/ui/Icon";
import { Banner, Button, ButtonLink, Hint } from "@/components/ui/primitives";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import styles from "../page.module.css";

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
    <div className={styles.page}>
      <header className={styles.nav}>
        <Brand />
        <ThemeToggle />
      </header>
      <main className={styles.auth}>
        <div className={styles.authCard}>
          <span className={styles.authIcon}>
            <Icon name="lock" size={20} />
          </span>
          <h1>Sign in to Studio</h1>
          <p className={styles.authLede}>
            Paste the Studio key your administrator gave you (the <code>STUDIO_API_KEY</code> of the
            server). It is only checked here — your browser keeps a signed sign-in for 12 hours, never
            the key itself.
          </p>
          <form onSubmit={submit} className={styles.authForm}>
            {demoKey && (
              <Banner tone="accent" role="note" data-testid="login-demo-hint">
                This is a demo install, so the key is <code>{demoKey}</code>.{" "}
                <button type="button" className={styles.linkBtn} onClick={() => setKey(demoKey)}>
                  Use it
                </button>
                <br />
                Before real use, set your own <code>STUDIO_API_KEY</code> in the server&apos;s{" "}
                <code>.env</code> file and restart.
              </Banner>
            )}
            <label>
              Studio key
              <input
                type="password"
                autoComplete="current-password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                data-testid="login-key"
                required
                autoFocus
              />
              {!demoKey && (
                <Hint data-testid="login-key-hint">
                  Don&apos;t have it? Ask whoever runs this server. They can read it with{" "}
                  <code>docker compose exec web printenv STUDIO_API_KEY</code>.
                </Hint>
              )}
            </label>
            {error && <Banner tone="danger">{error}</Banner>}
            <Button type="submit" variant="primary" size="lg" busy={busy} disabled={busy} data-testid="login-submit">
              {busy ? "Checking…" : "Sign in"}
            </Button>
            {sso && (
              <>
                <span className={styles.divider}>or</span>
                <ButtonLink
                  variant="secondary"
                  size="lg"
                  icon="user"
                  href={`/api/studio/oidc/login?return_to=${encodeURIComponent(next)}`}
                >
                  Sign in with SSO
                </ButtonLink>
              </>
            )}
          </form>
        </div>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
