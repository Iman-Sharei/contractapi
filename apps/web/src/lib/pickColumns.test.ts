import { describe, expect, it } from "vitest";
import { defaultSafeColumns, endpointDefaults, ensurePrimaryKey, formatApiPath, hasDecimalColumns, initialPicks } from "./pickColumns";
import type { TableInfo } from "./types";

const table: TableInfo = {
  name: "customers",
  schema: "public",
  kind: "table",
  columns: [
    { name: "id", type: "uuid", nullable: false, primary_key: true, sensitive: false },
    { name: "email", type: "text", nullable: false, primary_key: false, sensitive: false },
    { name: "ssn", type: "text", nullable: true, primary_key: false, sensitive: true },
    { name: "name", type: "text", nullable: true, primary_key: false, sensitive: false },
  ],
  foreign_keys: [],
  primary_keys: ["id"],
  sensitive_columns: ["ssn"],
};

describe("pickColumns", () => {
  it("defaultSafeColumns skips sensitive and puts pk first", () => {
    expect(defaultSafeColumns(table)).toEqual(["id", "email", "name"]);
  });

  it("ensurePrimaryKey inserts missing pk", () => {
    expect(ensurePrimaryKey(["email", "name"], table)).toEqual(["id", "email", "name"]);
  });

  it("formatApiPath supports empty prefix (no version)", () => {
    expect(formatApiPath("", "/customers")).toBe("/customers");
    expect(formatApiPath("/v1", "/customers")).toBe("/v1/customers");
    expect(formatApiPath("/v1/", "/customers")).toBe("/v1/customers");
  });
});

describe("hasDecimalColumns", () => {
  const t = {
    name: "orders",
    schema: "public",
    kind: "table",
    columns: [
      { name: "id", type: "INTEGER", nullable: false, primary_key: true, sensitive: false },
      { name: "total", type: "NUMERIC(12, 2)", nullable: false, primary_key: false, sensitive: false },
    ],
    primary_keys: ["id"],
    sensitive_columns: [],
    foreign_keys: [],
  } as unknown as TableInfo;
  it("is true only when a picked column is a decimal", () => {
    expect(hasDecimalColumns([t], ["public.orders"], { "public.orders": ["id", "total"] })).toBe(true);
    expect(hasDecimalColumns([t], ["public.orders"], { "public.orders": ["id"] })).toBe(false);
  });
});

describe("initialPicks", () => {
  const mk = (name: string) => ({ ...table, name }) as TableInfo;
  it("ticks every table of a small database and none of a big one", () => {
    expect(Object.keys(initialPicks([mk("a"), mk("b")]))).toEqual(["public.a", "public.b"]);
    expect(initialPicks(["a", "b", "c", "d", "e", "f"].map(mk))).toEqual({});
  });
});

describe("endpointDefaults", () => {
  const W = ["POST", "PATCH", "PUT", "DELETE"];
  it("uses next-page links and full writes only with a unique id", () => {
    expect(endpointDefaults(table, true, W)).toMatchObject({ uniqueId: true, mode: "cursor", methods: ["GET", ...W] });
  });
  it("falls back to page numbers and create-only writes without one", () => {
    const view = { ...table, kind: "view", primary_keys: [] } as TableInfo;
    const d = endpointDefaults(view, true, W);
    expect(d).toMatchObject({ uniqueId: false, mode: "offset", methods: ["GET", "POST"] });
    expect(endpointDefaults(view, false, W).methods).toEqual(["GET"]);
  });
});
