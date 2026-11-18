import { NextRequest, NextResponse } from "next/server";
import {
  OIDC_STATE_COOKIE,
  STUDIO_SESSION_COOKIE,
  backendBase,
  isCrossSiteWrite,
  oidcCookieName,
  problem,
  studioKeyForRequest,
} from "@/lib/studioAuth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(req: NextRequest, pathParts: string[]) {
  const env = process.env;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  if (isCrossSiteWrite(req.method, req.headers.get("origin"), host)) {
    return problem(403, "Forbidden", "Cross-site request blocked.");
  }

  // OIDC login endpoints are public on the backend; everything else needs a Studio session.
  const isOidcRoute = pathParts[0] === "oidc";
  const key = await studioKeyForRequest(req.cookies.get(STUDIO_SESSION_COOKIE)?.value, env);
  const oidcCookie = req.cookies.get(oidcCookieName(env))?.value;
  if (!isOidcRoute && !key && !oidcCookie) {
    return problem(401, "Unauthorized", "Sign in to Studio first.");
  }

  const sub = pathParts.map(encodeURIComponent).join("/");
  const url = new URL(req.url);
  const target = `${backendBase(env)}/studio/${sub}${url.search}`;

  const headers = new Headers();
  for (const h of ["content-type", "accept", "authorization"]) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  if (key) headers.set("X-API-Key", key);
  // Forward only the OIDC cookies the backend needs (session + login state for /oidc/callback).
  const forwarded = [oidcCookieName(env), OIDC_STATE_COOKIE]
    .map((name) => [name, req.cookies.get(name)?.value] as const)
    .filter(([, v]) => v)
    .map(([name, v]) => `${name}=${v}`);
  if (forwarded.length) headers.set("cookie", forwarded.join("; "));

  // manual: OIDC login answers with a redirect to the IdP that the browser must follow.
  const init: RequestInit = { method: req.method, headers, cache: "no-store", redirect: "manual" };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const outHeaders = new Headers();
  for (const h of ["content-type", "content-disposition", "x-request-id", "cache-control", "location"]) {
    const v = upstream.headers.get(h);
    if (v) outHeaders.set(h, v);
  }
  for (const c of upstream.headers.getSetCookie?.() ?? []) {
    outHeaders.append("set-cookie", c);
  }
  return new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: outHeaders,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
