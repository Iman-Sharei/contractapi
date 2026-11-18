import { NextRequest, NextResponse } from "next/server";
import {
  SESSION_MAX_AGE_SECONDS,
  STUDIO_SESSION_COOKIE,
  backendBase,
  createSessionToken,
  isCrossSiteWrite,
  oidcCookieName,
  problem,
  sameSecret,
  serverStudioKey,
  signInHint,
  studioKeyForRequest,
} from "@/lib/studioAuth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function crossSite(req: NextRequest) {
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  return isCrossSiteWrite(req.method, req.headers.get("origin"), host);
}

/** Is this browser signed in to Studio? */
export async function GET(req: NextRequest) {
  const env = process.env;
  const authenticated = Boolean(
    (await studioKeyForRequest(req.cookies.get(STUDIO_SESSION_COOKIE)?.value, env)) ||
      req.cookies.get(oidcCookieName(env))?.value,
  );
  return NextResponse.json({ authenticated, ...signInHint(env) });
}

/** Sign in with the Studio key. The cookie gets a signed, expiring token — never the key. */
export async function POST(req: NextRequest) {
  const env = process.env;
  if (crossSite(req)) return problem(403, "Forbidden", "Cross-site request blocked.");
  const expected = serverStudioKey(env);
  if (!expected) {
    return problem(500, "Misconfigured", "STUDIO_API_KEY is not set on the Studio server.");
  }
  const body = (await req.json().catch(() => null)) as { key?: unknown } | null;
  const key = typeof body?.key === "string" ? body.key.trim() : "";
  if (!key || key.length > 512) {
    return problem(400, "Bad Request", "Enter your Studio key.");
  }
  if (!sameSecret(key, expected)) {
    return problem(401, "Unauthorized", "That Studio key is not valid.");
  }

  // The Studio server must also be able to reach the API with its key.
  let upstream: Response;
  try {
    upstream = await fetch(`${backendBase(env)}/studio/health`, {
      headers: { "X-API-Key": expected },
      cache: "no-store",
    });
  } catch {
    return problem(502, "Bad Gateway", "Cannot reach the contractapi server. Is it running?");
  }
  if (!upstream.ok) {
    return problem(
      502,
      "Bad Gateway",
      "The API rejected the Studio server's key. STUDIO_API_KEY must match on the Studio and the API.",
    );
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(STUDIO_SESSION_COOKIE, await createSessionToken(env), {
    httpOnly: true,
    sameSite: "strict",
    secure: env.NODE_ENV === "production" && env.STUDIO_COOKIE_INSECURE !== "true",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
  return res;
}

/** Sign out. */
export async function DELETE(req: NextRequest) {
  if (crossSite(req)) return problem(403, "Forbidden", "Cross-site request blocked.");
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(STUDIO_SESSION_COOKIE);
  return res;
}
