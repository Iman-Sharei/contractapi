import { describe, expect, it } from "vitest";
import {
  createSessionToken,
  DEMO_STUDIO_KEY,
  devAutologin,
  signInHint,
  isCrossSiteWrite,
  looksLikeLiveSession,
  studioKeyForRequest,
  verifySessionToken,
} from "./studioAuth";

const env = { STUDIO_API_KEY: "server-key-123", NODE_ENV: "production" };

describe("signed Studio session", () => {
  it("round-trips and never contains the key", async () => {
    const token = await createSessionToken(env);
    expect(token).not.toContain("server-key-123");
    expect(await verifySessionToken(token, env)).toBe(true);
    expect(await studioKeyForRequest(token, env)).toBe("server-key-123");
  });
  it("rejects tampering, expiry and key rotation", async () => {
    const token = await createSessionToken(env);
    const [v, exp, nonce, sig] = token.split(".");
    expect(await verifySessionToken(`${v}.${Number(exp) + 999}.${nonce}.${sig}`, env)).toBe(false);
    expect(await verifySessionToken(token, env, Date.now() + 13 * 3600 * 1000)).toBe(false);
    expect(await verifySessionToken(token, { ...env, STUDIO_API_KEY: "rotated" })).toBe(false);
    expect(await studioKeyForRequest("garbage", env)).toBeNull();
    expect(await studioKeyForRequest(undefined, env)).toBeNull();
  });
  it("middleware shape check follows expiry", async () => {
    const token = await createSessionToken(env);
    expect(looksLikeLiveSession(token)).toBe(true);
    expect(looksLikeLiveSession(token, Date.now() + 13 * 3600 * 1000)).toBe(false);
    expect(looksLikeLiveSession("server-key-123")).toBe(false);
  });
  it("dev autologin never applies to production builds", () => {
    expect(devAutologin({ ...env, STUDIO_DEV_AUTOLOGIN: "true" })).toBe(false);
    expect(devAutologin({ NODE_ENV: "development", STUDIO_DEV_AUTOLOGIN: "true" })).toBe(true);
  });
});

describe("signInHint", () => {
  it("shows the key only while the server uses the public demo default", () => {
    expect(signInHint({ STUDIO_API_KEY: DEMO_STUDIO_KEY })).toEqual({ demoKey: DEMO_STUDIO_KEY });
    expect(signInHint({ STUDIO_API_KEY: "real-secret-key" })).toEqual({ demoKey: null });
    expect(signInHint({})).toEqual({ demoKey: null });
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
