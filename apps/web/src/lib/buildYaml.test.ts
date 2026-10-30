import { describe, expect, it } from "vitest";
import { buildYaml } from "./api";
import type { ApiSpecDraft } from "./types";

const sample: ApiSpecDraft = {
  database: { url: "postgresql://x/y" },
  app: {
    title: "T",
    version: "1.0.0",
    description: "d",
    read_only: true,
    auth: "api_key",
    api_prefix: "/v1",
    environment: "staging",
    ip_allowlist: ["10.0.0."],
    webhooks: [{ url: "https://example.com/hook", events: ["create"], secret: "s" }],
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
    expect(yaml).toContain("environment: staging");
    expect(yaml).toContain("ip_allowlist:");
    expect(yaml).toContain("webhooks:");
    expect(yaml).toContain("ndjson_export: true");
    expect(yaml).toContain("parquet_export: true");
    expect(yaml).toContain("search_param: q");
    expect(yaml).toContain("ttl_seconds: 60");
    expect(yaml).toContain("required_for_writes: true");
  });
});
