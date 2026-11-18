import { NextRequest, NextResponse } from "next/server";
import {
  SESSION_MAX_AGE_SECONDS,
  STUDIO_SESSION_COOKIE,
  backendBase,
  isCrossSiteWrite,
  oidcCookieName,
  problem,
  resolveStudioKey,
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
    resolveStudioKey(req.cookies.get(STUDIO_SESSION_COOKIE)?.value, env) ||
      req.cookies.get(oidcCookieName(env))?.value,
  );
  return NextResponse.json({ authenticated });
}

/** Sign in with the Studio key: verified against the backend before the cookie is set. */
export async function POST(req: NextRequest) {
  if (crossSite(req)) return problem(403, "Forbidden", "Cross-site request blocked.");
  const body = (await req.json().catch(() => null)) as { key?: unknown } | null;
  const key = typeof body?.key === "string" ? body.key.trim() : "";
  if (!key || key.length > 512) {
    return problem(400, "Bad Request", "Enter your Studio key.");
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${backendBase(process.env)}/studio/health`, {
      headers: { "X-API-Key": key },
      cache: "no-store",
    });
  } catch {
    return problem(502, "Bad Gateway", "Cannot reach the contractapi server. Is it running?");
  }
  if (!upstream.ok) {
    return problem(401, "Unauthorized", "That Studio key is not valid.");
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(STUDIO_SESSION_COOKIE, key, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production" && process.env.STUDIO_COOKIE_INSECURE !== "true",
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
