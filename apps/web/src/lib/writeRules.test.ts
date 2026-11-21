import { describe, expect, it } from "vitest";
import { formatColumnValues, managedColumns, nestableRelations, parseColumnValues, toggleNested } from "./writeRules";
import type { EndpointDraft } from "./types";

const ep = (over: Partial<EndpointDraft> = {}): EndpointDraft => ({
  name: "people",
  path: "/people",
  table: "people",
  schema: "public",
  methods: ["GET", "POST"],
  primary_key: "id",
  fields: ["id", "name"],
  filters: [],
  sortable: [],
  ...over,
});

describe("column values", () => {
  it("types values like YAML and round-trips", () => {
    const { values, errors } = parseColumnValues('status = pending\nscore = 7\nactive = true\nnote = null\ncode = 007\nlabel = "12"');
    expect(errors).toEqual([]);
    expect(values).toEqual({ status: "pending", score: 7, active: true, note: null, code: "007", label: "12" });
    expect(parseColumnValues(formatColumnValues(values)).values).toEqual(values);
  });

  it("reports bad lines instead of dropping them", () => {
    const { values, errors } = parseColumnValues("status pending\nbad name = 1\n\nok = 1");
    expect(values).toEqual({ ok: 1 });
    expect(errors).toEqual(["Line 1: write it as column = value", 'Line 2: "bad name" is not a column name']);
  });
});

describe("nested writes and managed columns", () => {
  const rel = { name: "orders", table: "orders", schema: "public", local_key: "id", foreign_key: "person_id", fields: ["id"], primary_key: "id", max_per_parent: 50 };
  it("only offers one_to_many relations", () => {
    const e = ep({ relations: [{ ...rel, type: "one_to_many" }, { ...rel, name: "owner", type: "many_to_one" }] });
    expect(nestableRelations(e).map((r) => r.name)).toEqual(["orders"]);
    expect(toggleNested(e, "orders", true)).toEqual(["orders"]);
    expect(toggleNested({ ...e, nested_writes: ["orders"] }, "orders", false)).toEqual([]);
  });
  it("lists columns the API writes itself", () => {
    expect(managedColumns(ep({ fixed_values: { tenant: "a" }, timestamps: { updated_at: "updated_at" } }))).toEqual(["tenant", "updated_at"]);
  });
});
