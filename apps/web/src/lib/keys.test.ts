import { describe, expect, it } from "vitest";
import { keyAccess, keyApis, keyLastUsed, keyStatus } from "./keys";

const now = 1_800_000_000;

describe("API key rows", () => {
  it("names the APIs and the access", () => {
    expect(keyApis({ apis: ["*"] })).toBe("All APIs");
    expect(keyApis({ apis: ["hr", "shop"] })).toBe("hr, shop");
    expect([keyAccess({ access: "read" }), keyAccess({ access: "write" })]).toEqual(["Read only", "Read and change"]);
  });
  it("says whether the key still works", () => {
    const base = { revoked: false, expired: false, expires_at: null };
    expect(keyStatus(base, now)).toBe("Active");
    expect(keyStatus({ ...base, expires_at: now + 3 * 86_400 }, now)).toBe("Expires in 3 days");
    expect(keyStatus({ ...base, expires_at: now + 600 }, now)).toBe("Expires within a day");
    expect(keyStatus({ ...base, expires_at: now - 1 }, now)).toBe("Expired");
    expect(keyStatus({ ...base, revoked: true }, now)).toBe("Revoked");
  });
  it("says when it was last used", () => {
    expect(keyLastUsed({ last_used_at: null }, now)).toBe("Never used");
    expect(keyLastUsed({ last_used_at: now - 120 }, now)).toBe("Used in the last hour");
    expect(keyLastUsed({ last_used_at: now - 5 * 3600 }, now)).toBe("Used 5 h ago");
    expect(keyLastUsed({ last_used_at: now - 3 * 86_400 }, now)).toBe("Used 3 days ago");
  });
});
