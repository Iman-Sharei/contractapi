import { describe, expect, it } from "vitest";
import { defaultSafeColumns, ensurePrimaryKey, formatApiPath } from "./pickColumns";
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
