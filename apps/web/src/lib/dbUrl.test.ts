import { describe, expect, it } from "vitest";
import { DEMO_PG, buildPgUrl, missingPgFields, parsePgUrl } from "./dbUrl";

describe("dbUrl", () => {
  it("builds the demo URL", () => {
    expect(buildPgUrl(DEMO_PG)).toBe("postgresql://postgres:postgres@db:5432/app");
  });
  it("encodes special characters in credentials and round-trips", () => {
    const f = { host: "pg.example.com", port: "6543", database: "sales", user: "ana@corp", password: "p@ss:w/rd" };
    const url = buildPgUrl(f);
    expect(url).toBe("postgresql://ana%40corp:p%40ss%3Aw%2Frd@pg.example.com:6543/sales");
    expect(parsePgUrl(url)).toEqual(f);
  });
  it("parses secret references and rejects non-postgres text", () => {
    expect(parsePgUrl("postgresql://u:${secret:db-x}@h:5432/d")?.password).toBe("${secret:db-x}");
    expect(parsePgUrl("duckdb:///:memory:")).toBeNull();
  });
  it("explains what is missing in plain words", () => {
    expect(missingPgFields({ host: "", port: "x", database: "", user: "", password: "" })).toEqual([
      "server address",
      "database name",
      "user name",
      "a numeric port",
    ]);
    expect(missingPgFields(DEMO_PG)).toEqual([]);
  });
});
