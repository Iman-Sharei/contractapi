/**
 * Studio BFF auth helpers (server-side only; no secrets reach the browser).
 *
 * The browser proves it is a Studio admin with either:
 *  - the httpOnly session cookie set by POST /api/session (holds the STUDIO_API_KEY), or
 *  - the backend OIDC cookie (same-site deployments).
 *
 * ponytail: the session cookie stores the raw Studio key (httpOnly, SameSite=Strict).
 * Ceiling: no per-user identity or server-side revocation; upgrade path is a signed,
 * expiring session token minted by the backend.
 */

type Env = Record<string, string | undefined>;

export const STUDIO_SESSION_COOKIE = "contractapi_studio";
export const SESSION_MAX_AGE_SECONDS = 12 * 60 * 60;

export function backendBase(env: Env): string {
  return (env.API_BASE || env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
}

export function oidcCookieName(env: Env): string {
  return env.STUDIO_OIDC_COOKIE_NAME || "contractapi_oidc";
}

/** Local-dev convenience only: never active in a production build. */
export function devAutologinKey(env: Env): string | null {
  if (env.NODE_ENV === "production" || env.STUDIO_DEV_AUTOLOGIN !== "true") return null;
  return env.STUDIO_API_KEY || "dev-studio-key-change-me";
}

/** Studio key to send upstream, or null when the caller is not logged in. */
export function resolveStudioKey(sessionKey: string | undefined, env: Env): string | null {
  return sessionKey || devAutologinKey(env);
}

/** True for a state-changing request whose Origin is not this site (CSRF). */
export function isCrossSiteWrite(method: string, origin: string | null, host: string | null): boolean {
  if (["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) return false;
  if (!origin) return false; // non-browser client; browsers always send Origin on POST/PUT/PATCH/DELETE
  try {
    return new URL(origin).host !== host;
  } catch {
    return true;
  }
}

export function problem(status: number, title: string, detail: string) {
  return new Response(JSON.stringify({ type: "about:blank", title, status, detail }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}
