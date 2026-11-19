import { describe, expect, it } from "vitest";
import { buildClientSnippet } from "./api";

describe("buildClientSnippet", () => {
  it("targets the API's own mount, like Try it does", () => {
    const s = buildClientSnippet({
      base: "http://localhost:8000",
      path: "/customers",
      method: "GET",
      authMode: "api_key",
      query: "limit=5",
      mount: "/apis/shop",
    });
    expect(s.curl).toContain('"http://localhost:8000/apis/shop/customers?limit=5"');
    expect(s.python).toContain("http://localhost:8000/apis/shop/customers?limit=5");
  });
});
