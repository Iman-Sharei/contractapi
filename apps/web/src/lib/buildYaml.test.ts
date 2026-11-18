import { describe, expect, it } from "vitest";
import { buildYaml } from "./api";
import type { ApiSpecDraft } from "./types";

const sample: ApiSpecDraft = {
  database: { url: "postgresql://x/y", driver: "postgres" },
  app: {
    title: "T",
    version: "1.0.0",
    description: "d",
    read_only: true,
    auth: "api_key",
    api_prefix: "",
    environment: "staging",
    ip_allowlist: ["10.0.0."],
    webhooks: [{ url: "https://example.com/hook", events: ["create"], secret: "s" }],
    jwt: {
      issuer: "contractapi",
      audience: "clients",
      algorithm: "HS256",
      access_ttl_minutes: 30,
      refresh_ttl_days: 14,
    },
    rbac: [{ role: "analyst", endpoints: { customers: ["id", "email"] } }],
    cache: { enabled: true, ttl_seconds: 30 },
    idempotency: { enabled: true, required_for_writes: true, ttl_seconds: 60 },
    rate_limit: { enabled: true, requests_per_minute: 60 },
  },
  endpoints: [
    {
      name: "customers",
      path: "/customers",
      table: "customers",
      schema: "public",
      methods: ["GET"],
      primary_key: "id",
      fields: ["id", "email"],
      filters: ["email"],
      sortable: ["id"],
      search_param: "q",
      ndjson_export: true,
      parquet_export: true,
      sql_params: [],
      validations: [{ field: "email", format: "email", ge: null, le: 10 }],
    },
  ],
};

describe("buildYaml", () => {
  it("includes previously missing contract fields", () => {
    const yaml = buildYaml(sample);
    expect(yaml).toContain('api_prefix: ""');
    expect(yaml).toContain("environment: staging");
    expect(yaml).toContain("ip_allowlist:");
    expect(yaml).toContain("webhooks:");
    expect(yaml).toContain("jwt:");
    expect(yaml).toContain("access_ttl_minutes: 30");
    expect(yaml).toContain("rbac:");
    expect(yaml).toContain("ndjson_export: true");
    expect(yaml).toContain("parquet_export: true");
    expect(yaml).toContain("search_param: q");
    expect(yaml).toContain("ttl_seconds: 60");
    expect(yaml).toContain("required_for_writes: true");
  });
});

describe("buildYaml quoting", () => {
  const tricky: ApiSpecDraft = {
    ...sample,
    database: { url: "duckdb:///:memory:", driver: "duckdb" },
    app: { ...sample.app, title: "Sales: 2026 #1", version: "1.0" },
    endpoints: [
      {
        ...sample.endpoints[0],
        name: "stats",
        path: "/stats",
        sql: "SELECT id, 'a: b' AS note\nFROM t WHERE x::int > :min",
      },
      {
        ...sample.endpoints[0],
        relations: [
          {
            name: "items", table: "items", schema: "public", type: "one_to_many", local_key: "id",
            foreign_key: "order_id", fields: ["id"], primary_key: "id", max_per_parent: 5,
            soft_delete_column: "deleted_at",
          },
        ],
      },
    ],
  };

  it("quotes values YAML would misread and keeps every field", () => {
    const yaml = buildYaml(tricky);
    expect(yaml).toContain('url: "duckdb:///:memory:"');
    expect(yaml).toContain('title: "Sales: 2026 #1"');
    expect(yaml).toContain('version: "1.0"');
    expect(yaml).toContain("sql: |-\n      SELECT id, 'a: b' AS note\n      FROM t WHERE x::int > :min");
    expect(yaml).toContain("soft_delete_column: deleted_at");
    expect(yaml).toContain("enabled: true");
  });

  it("writes the YAML for the round-trip check when asked", async () => {
    if (!process.env.YAML_ROUNDTRIP_OUT) return;
    const { writeFileSync } = await import("node:fs");
    writeFileSync(process.env.YAML_ROUNDTRIP_OUT, buildYaml(tricky));
  });
});
