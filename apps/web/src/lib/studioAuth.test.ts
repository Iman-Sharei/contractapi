import { describe, expect, it } from "vitest";
import { devAutologinKey, isCrossSiteWrite, resolveStudioKey } from "./studioAuth";

describe("resolveStudioKey", () => {
  it("is null without a session (the BFF must not inject a key)", () => {
    expect(resolveStudioKey(undefined, { STUDIO_API_KEY: "k" })).toBeNull();
  });
  it("uses the session cookie value", () => {
    expect(resolveStudioKey("from-cookie", {})).toBe("from-cookie");
  });
  it("dev autologin never applies to production builds", () => {
    const env = { NODE_ENV: "production", STUDIO_DEV_AUTOLOGIN: "true", STUDIO_API_KEY: "k" };
    expect(devAutologinKey(env)).toBeNull();
    expect(devAutologinKey({ ...env, NODE_ENV: "development" })).toBe("k");
  });
});

describe("isCrossSiteWrite", () => {
  it("blocks writes from another origin", () => {
    expect(isCrossSiteWrite("POST", "https://evil.example", "studio.local:3000")).toBe(true);
  });
  it("allows same-origin writes and all reads", () => {
    expect(isCrossSiteWrite("POST", "http://studio.local:3000", "studio.local:3000")).toBe(false);
    expect(isCrossSiteWrite("GET", "https://evil.example", "studio.local:3000")).toBe(false);
  });
  it("treats a malformed Origin as cross-site", () => {
    expect(isCrossSiteWrite("DELETE", "null", "studio.local:3000")).toBe(true);
  });
});
