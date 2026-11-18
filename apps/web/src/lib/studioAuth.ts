/**
 * Studio BFF auth helpers (server-side only; no secrets reach the browser).
 *
 * The browser proves it is a Studio admin with either:
 *  - a signed, expiring session cookie minted by POST /api/session after the user typed the
 *    Studio key. The cookie holds no secret: `v1.<expiresAt>.<nonce>.<HMAC>`. The BFF then
 *    calls the backend with the server's own STUDIO_API_KEY.
 *  - the backend OIDC cookie (SSO), verified by the backend on every call.
 *
 * Signing key = HMAC(STUDIO_SESSION_SECRET || STUDIO_API_KEY, purpose). Rotating either one
 * signs everybody out (server-side revocation without a session store).
 */

type Env = Record<string, string | undefined>;

export const STUDIO_SESSION_COOKIE = "contractapi_studio";
export const OIDC_STATE_COOKIE = "contractapi_oidc_state";
export const SESSION_MAX_AGE_SECONDS = 12 * 60 * 60;
const SESSION_PURPOSE = "contractapi-studio-session-v1";

export function backendBase(env: Env): string {
  return (env.API_BASE || env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
}

export function oidcCookieName(env: Env): string {
  return env.STUDIO_OIDC_COOKIE_NAME || "contractapi_oidc";
}

/** The server's Studio key (never sent to the browser). */
export function serverStudioKey(env: Env): string | null {
  return env.STUDIO_API_KEY || null;
}

/** Local-dev convenience only: never active in a production build. */
export function devAutologin(env: Env): boolean {
  return env.NODE_ENV !== "production" && env.STUDIO_DEV_AUTOLOGIN === "true";
}

// ---- signed session tokens (Web Crypto: works in Node route handlers and the edge) ------

const enc = new TextEncoder();

function b64url(bytes: ArrayBuffer): string {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(keyMaterial: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(keyMaterial),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
}

async function signingKey(env: Env): Promise<string | null> {
  const root = env.STUDIO_SESSION_SECRET || env.STUDIO_API_KEY;
  return root ? hmac(root, SESSION_PURPOSE) : null;
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function createSessionToken(env: Env, nowMs = Date.now()): Promise<string> {
  const key = await signingKey(env);
  if (!key) throw new Error("STUDIO_API_KEY is not configured on the Studio server.");
  const exp = Math.floor(nowMs / 1000) + SESSION_MAX_AGE_SECONDS;
  const nonce = b64url(crypto.getRandomValues(new Uint8Array(16)).buffer);
  const body = `v1.${exp}.${nonce}`;
  return `${body}.${await hmac(key, body)}`;
}

/** Signature + expiry check. */
export async function verifySessionToken(
  token: string | undefined,
  env: Env,
  nowMs = Date.now(),
): Promise<boolean> {
  if (!token) return false;
  const parts = token.split(".");
  if (parts.length !== 4 || parts[0] !== "v1") return false;
  const exp = Number(parts[1]);
  if (!Number.isFinite(exp) || exp * 1000 < nowMs) return false;
  const key = await signingKey(env);
  if (!key) return false;
  return timingSafeEqual(parts[3], await hmac(key, parts.slice(0, 3).join(".")));
}

/** Cheap shape/expiry check for middleware (UX redirect only; route handlers verify the HMAC). */
export function looksLikeLiveSession(token: string | undefined, nowMs = Date.now()): boolean {
  const parts = token?.split(".") ?? [];
  return parts.length === 4 && parts[0] === "v1" && Number(parts[1]) * 1000 > nowMs;
}

/** Studio key to send upstream for this request, or null when the caller is not signed in. */
export async function studioKeyForRequest(sessionToken: string | undefined, env: Env): Promise<string | null> {
  if (devAutologin(env)) return serverStudioKey(env) || "dev-studio-key-change-me";
  return (await verifySessionToken(sessionToken, env)) ? serverStudioKey(env) : null;
}

export function sameSecret(a: string, b: string): boolean {
  return timingSafeEqual(a, b);
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
