import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function backendBase() {
  return (
    process.env.API_BASE ||
    process.env.NEXT_PUBLIC_API_BASE ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

function dataKey() {
  return process.env.DATA_API_KEY || process.env.NEXT_PUBLIC_DATA_API_KEY || "dev-data-key";
}

async function proxy(req: NextRequest, pathParts: string[]) {
  const sub = pathParts.map(encodeURIComponent).join("/");
  const url = new URL(req.url);
  const target = `${backendBase()}/data/${sub}${url.search}`;

  const headers = new Headers();
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);

  // Prefer client-forwarded auth; otherwise inject server-side data key for api_key mode.
  const auth = req.headers.get("authorization");
  const clientKey = req.headers.get("x-api-key");
  if (auth) headers.set("authorization", auth);
  else if (clientKey) headers.set("X-API-Key", clientKey);
  else headers.set("X-API-Key", dataKey());

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const outHeaders = new Headers();
  upstream.headers.forEach((v, k) => {
    if (["content-type", "link", "etag", "x-request-id", "idempotent-replayed"].includes(k)) {
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
