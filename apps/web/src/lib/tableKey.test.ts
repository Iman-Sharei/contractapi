import { describe, expect, it } from "vitest";
import { parseTableKey, tableKey } from "./tableKey";

describe("tableKey", () => {
  it("joins schema and name", () => {
    expect(tableKey({ schema: "sales", name: "orders" })).toBe("sales.orders");
  });

  it("parses keys", () => {
    expect(parseTableKey("sales.orders")).toEqual({ schema: "sales", name: "orders" });
    expect(parseTableKey("orders")).toEqual({ schema: "public", name: "orders" });
  });
});
