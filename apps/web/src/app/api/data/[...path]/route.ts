import { NextRequest, NextResponse } from "next/server";
import {
  STUDIO_SESSION_COOKIE,
  backendBase,
  isCrossSiteWrite,
  oidcCookieName,
  problem,
  studioKeyForRequest,
  toPublicUrls,
} from "@/lib/studioAuth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Studio "try it" proxy for the data plane — only for signed-in Studio users. */
async function proxy(req: NextRequest, pathParts: string[]) {
  const env = process.env;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  if (isCrossSiteWrite(req.method, req.headers.get("origin"), host)) {
    return problem(403, "Forbidden", "Cross-site request blocked.");
  }
  const signedIn =
    (await studioKeyForRequest(req.cookies.get(STUDIO_SESSION_COOKIE)?.value, env)) ||
    req.cookies.get(oidcCookieName(env))?.value;
  if (!signedIn) {
    return problem(401, "Unauthorized", "Sign in to Studio first.");
  }

  const sub = pathParts.map(encodeURIComponent).join("/");
  const url = new URL(req.url);
  // /api/data/apis/<name>/... → /apis/<name>/... ; everything else → the primary API under /data.
  const target =
    pathParts[0] === "apis"
      ? `${backendBase(env)}/${sub}${url.search}`
      : `${backendBase(env)}/data/${sub}${url.search}`;

  const headers = new Headers();
  for (const h of ["content-type", "accept", "if-match", "if-none-match", "idempotency-key"]) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  // Prefer client-supplied auth (testing a JWT/key); otherwise the server-side data key.
  const auth = req.headers.get("authorization");
  const clientKey = req.headers.get("x-api-key");
  const dataKey = env.DATA_API_KEY;
  if (auth) headers.set("authorization", auth);
  else if (clientKey) headers.set("X-API-Key", clientKey);
  else if (dataKey) headers.set("X-API-Key", dataKey);

  const init: RequestInit = { method: req.method, headers, cache: "no-store" };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const outHeaders = new Headers();
  upstream.headers.forEach((v, k) => {
    if (["link", "location"].includes(k)) {
      outHeaders.set(k, toPublicUrls(v, env)); // never show the internal Docker hostname
    } else if (["content-type", "etag", "x-request-id", "idempotent-replayed", "retry-after"].includes(k)) {
      outHeaders.set(k, v);
    }
  });
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
