"use client";

import { useState } from "react";
import { Banner, Button, Hint } from "@/components/ui/primitives";
import { testCompanyLogin } from "@/lib/api";
import type { JwtConfigDraft, LoginServerInfo } from "@/lib/types";
import styles from "./editor.module.css";
import { emptyJwt, type EditorState } from "./useEditorState";

/** Login tokens: signed by this server (testing, your own backend) or by the company login. */
export function JwtSection({ s }: { s: EditorState }) {
  const { spec, patchApp } = s;
  const jwt: JwtConfigDraft = { ...emptyJwt(), ...(spec.app.jwt ?? {}) };
  const company = jwt.provider === "oidc";
  const [check, setCheck] = useState<{ ok?: LoginServerInfo; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const patch = (p: Partial<JwtConfigDraft>) => {
    if ("issuer" in p || "jwks_url" in p) setCheck(null); // an old result would describe another server
    patchApp({ jwt: { ...jwt, ...p } });
  };

  if (spec.app.auth !== "jwt") {
    return (
      <>
        <h3>Login tokens</h3>
        <Hint>Used when &quot;Who can use it?&quot; is set to login tokens (Settings).</Hint>
      </>
    );
  }

  async function test() {
    setTesting(true);
    setCheck(null);
    try {
      setCheck({ ok: await testCompanyLogin(jwt.issuer, jwt.jwks_url) });
    } catch (e) {
      setCheck({ error: e instanceof Error ? e.message : "The login server could not be reached." });
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <h3>Login tokens</h3>
      <fieldset className={styles.plainFieldset}>
        <legend className={styles.legend}>Who signs the tokens callers send?</legend>
        <label className={styles.check}>
          <input
            type="radio"
            name="jwt-provider"
            checked={!company}
            onChange={() => patch({ provider: "contractapi", issuer: "contractapi", audience: "contractapi-clients" })}
          />
          This server: for testing, or when your own backend asks Studio for tokens
        </label>
        <label className={styles.check}>
          <input
            type="radio"
            name="jwt-provider"
            checked={company}
            onChange={() => patch({ provider: "oidc", issuer: "", audience: "", algorithm: "HS256" })}
            data-testid="jwt-provider-company"
          />
          Your company login (Keycloak, Azure AD, Okta, Google, Auth0…)
        </label>
      </fieldset>

      {company ? (
        <>
          <div className={styles.twoCol}>
            <label>
              Login server address
              <input
                value={jwt.issuer}
                onChange={(e) => patch({ issuer: e.target.value })}
                placeholder="https://login.example.com/realms/main"
                spellCheck={false}
                data-testid="jwt-issuer"
              />
              <Hint>Exactly as in the tokens&apos; &quot;iss&quot; field (the issuer).</Hint>
            </label>
            <label>
              Audience
              <input
                value={jwt.audience}
                onChange={(e) => patch({ audience: e.target.value })}
                placeholder="the client ID or API identifier"
                spellCheck={false}
                data-testid="jwt-audience"
              />
              <Hint>Tokens made for other apps are refused.</Hint>
            </label>
          </div>
          <div className={styles.twoCol}>
            <label>
              Where are the roles in the token?
              <input
                value={jwt.roles_claim ?? "roles"}
                onChange={(e) => patch({ roles_claim: e.target.value })}
                placeholder="roles"
                spellCheck={false}
              />
              <Hint>Keycloak: realm_access.roles · Azure AD: roles · Okta: groups</Hint>
            </label>
            <label>
              Signing keys address (optional)
              <input
                value={jwt.jwks_url ?? ""}
                onChange={(e) => patch({ jwks_url: e.target.value || null })}
                placeholder="found automatically"
                spellCheck={false}
              />
            </label>
          </div>
          <div>
            <Button size="sm" variant="secondary" icon="refresh" onClick={test} disabled={testing || !jwt.issuer} busy={testing} data-testid="jwt-test">
              Test connection
            </Button>
          </div>
          {check?.ok && (
            <Banner tone="success" role="status">
              Connected: {check.ok.signing_keys} signing key{check.ok.signing_keys === 1 ? "" : "s"}
              {check.ok.algorithms.length ? ` (${check.ok.algorithms.join(", ")})` : ""}. Tokens from this
              login server will be checked against them.
            </Banner>
          )}
          {check?.error && <Banner tone="danger">{check.error}</Banner>}
          <Hint>
            Callers sign in with your company login and send its access token as
            <code> Authorization: Bearer …</code>. Roles from the token decide what they may see.
          </Hint>
        </>
      ) : (
        <div className={styles.twoCol}>
          <label>
            Token lifetime (minutes)
            <input
              type="number"
              min={1}
              max={1440}
              value={jwt.access_ttl_minutes}
              onChange={(e) => patch({ access_ttl_minutes: Number(e.target.value) || 15 })}
            />
          </label>
          <label>
            Refresh allowed for (days)
            <input
              type="number"
              min={1}
              max={90}
              value={jwt.refresh_ttl_days}
              onChange={(e) => patch({ refresh_ttl_days: Number(e.target.value) || 7 })}
            />
          </label>
          <Hint>Signed with the server&apos;s JWT_SECRET, which never appears in the API file.</Hint>
        </div>
      )}
    </>
  );
}
