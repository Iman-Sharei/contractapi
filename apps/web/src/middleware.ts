import { NextResponse, type NextRequest } from "next/server";
import { STUDIO_SESSION_COOKIE, devAutologin, looksLikeLiveSession, oidcCookieName } from "@/lib/studioAuth";

/**
 * Send signed-out visitors of /studio to /login. UX gate only: it checks the session's
 * shape and expiry; every /api route handler verifies the signature before calling the API.
 */
export function middleware(req: NextRequest) {
  const env = process.env;
  const signedIn =
    looksLikeLiveSession(req.cookies.get(STUDIO_SESSION_COOKIE)?.value) ||
    Boolean(req.cookies.get(oidcCookieName(env))?.value) ||
    devAutologin(env);
  if (signedIn) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/studio", "/studio/:path*"] };
