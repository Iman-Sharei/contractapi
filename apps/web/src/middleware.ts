import { NextResponse, type NextRequest } from "next/server";
import { STUDIO_SESSION_COOKIE, devAutologinKey, oidcCookieName } from "@/lib/studioAuth";

/** Send signed-out visitors of /studio to /login (the BFF re-checks every API call). */
export function middleware(req: NextRequest) {
  const env = process.env;
  const signedIn =
    req.cookies.get(STUDIO_SESSION_COOKIE)?.value ||
    req.cookies.get(oidcCookieName(env))?.value ||
    devAutologinKey(env);
  if (signedIn) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/studio", "/studio/:path*"] };
