import { describe, expect, it } from "vitest";
import { defaultPath, pathError, suggestPath } from "./pathRules";

describe("pathRules", () => {
  it("accepts normal resource paths", () => {
    expect(pathError("/order-items", "")).toBeNull();
    expect(pathError("/stats/daily_sales", "")).toBeNull();
  });
  it("rejects braces, spaces, quotes and uppercase", () => {
    expect(pathError("/docs/{evil} x'", "/v1")).toMatch(/lowercase/);
    expect(pathError("/Customers", "/v1")).toMatch(/customers/);
  });
  it("blocks built-in routes only without a prefix", () => {
    expect(pathError("/metrics", "")).toMatch(/built-in/);
    expect(pathError("/metrics", "/v1")).toBeNull();
  });
  it("suggests and defaults to valid paths", () => {
    expect(suggestPath("Order Items")).toBe("/order-items");
    expect(defaultPath("metrics", "")).toBe("/metrics-data");
    expect(defaultPath("orders", "")).toBe("/orders");
  });
});
