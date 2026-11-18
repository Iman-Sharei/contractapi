import { describe, expect, it } from "vitest";
import { safetyChecks } from "./safetyChecks";
import { curlSnippet, endpointUrl, pandasSnippet, pythonSnippet } from "./snippets";
import type { ApiSpecDraft } from "./types";

const input = {
  apiBase: "https://api.example.com/",
  mount: "/apis/shop",
  apiPrefix: "/v1",
  path: "/orders",
  auth: "api_key" as const,
};

describe("snippets", () => {
  it("builds the public URL from base, mount, prefix and path", () => {
    expect(endpointUrl(input)).toBe("https://api.example.com/apis/shop/v1/orders");
  });
  it("puts the right auth header in every language", () => {
    expect(curlSnippet(input)).toContain('-H "X-API-Key: YOUR_API_KEY"');
    expect(pythonSnippet({ ...input, apiKey: "dk_123" })).toContain('"X-API-Key": "dk_123"');
    expect(pandasSnippet({ ...input, auth: "jwt" })).toContain("Bearer YOUR_JWT");
    expect(curlSnippet({ ...input, auth: "none" })).not.toContain("-H");
  });
  it("pandas example follows cursor pages", () => {
    expect(pandasSnippet(input)).toContain('params["cursor"] = page["next_cursor"]');
  });
});

function spec(app: Partial<ApiSpecDraft["app"]>, methods = ["GET"]): ApiSpecDraft {
  return {
    database: { url: "postgresql://x" },
    app: {
      title: "t",
      version: "1",
      description: "",
      read_only: true,
      auth: "api_key",
      api_prefix: "/v1",
      rate_limit: { enabled: true, requests_per_minute: 120 },
      ...app,
    },
    endpoints: [{ name: "orders", path: "/orders", table: "orders", schema: "public", methods, primary_key: "id", fields: ["id"], filters: [], sortable: [] }],
  };
}

describe("safetyChecks", () => {
  it("is quiet for a read-only, keyed, rate-limited API", () => {
    expect(safetyChecks(spec({}))).toEqual([]);
  });
  it("warns about public writes in plain language", () => {
    const msgs = safetyChecks(spec({ auth: "none", read_only: false }, ["GET", "POST"])).map((f) => f.message);
    expect(msgs.some((m) => m.includes("Anyone who knows the URL"))).toBe(true);
    expect(msgs.some((m) => m.includes("anyone could change or delete rows"))).toBe(true);
  });
  it("flags a disabled rate limit", () => {
    const f = safetyChecks(spec({ rate_limit: { enabled: false, requests_per_minute: 1 } }));
    expect(f[0].message).toMatch(/Rate limit is off/);
  });
});
