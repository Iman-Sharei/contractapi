import { describe, expect, it } from "vitest";
import { breakingLines } from "./diffSummary";

describe("breakingLines", () => {
  it("lists removed operations, fields, filters and inputs; ignores additions", () => {
    const lines = breakingLines({
      breaking: true,
      summary: { added: 1, removed: 1, updated: 2 },
      changes: [
        { type: "NEW", method: "GET", path: "/v1/new" },
        { type: "DELETE", method: "DELETE", path: "/v1/orders/{item_id}" },
        { type: "UPDATE", method: "GET", path: "/v1/orders", breaking: true, removed_fields: ["total", "?status", "?status__in", "?status__ne"], added_fields: [] },
        { type: "UPDATE", method: "POST", path: "/v1/orders", breaking: true, removed_fields: ["body: note"] },
        { type: "UPDATE", method: "GET", path: "/v1/x", breaking: false, added_fields: ["a"] },
      ],
    });
    expect(lines).toEqual([
      "DELETE /v1/orders/{item_id} is removed",
      "GET /v1/orders no longer has field total, filter ?status",
      "POST /v1/orders no longer has input field note",
    ]);
  });
  it("shortens long lists", () => {
    const many = Array.from({ length: 12 }, (_, i) => ({ type: "DELETE" as const, method: "GET", path: `/p${i}` }));
    const lines = breakingLines({ breaking: true, summary: { added: 0, removed: 12, updated: 0 }, changes: many });
    expect(lines).toHaveLength(9);
    expect(lines[8]).toBe("…and 4 more");
  });
});
