export type ColumnInfo = {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  sensitive: boolean;
  comment?: string | null;
};

export type TableInfo = {
  name: string;
  schema: string;
  kind?: "table" | "view";
  columns: ColumnInfo[];
  foreign_keys: { column: string; ref_table: string; ref_column: string }[];
  primary_keys: string[];
  sensitive_columns: string[];
};

export type RelationDraft = {
  name: string;
  table: string;
  schema: string;
  type: "one_to_many" | "many_to_one";
  local_key: string;
  foreign_key: string;
  fields: string[];
  primary_key: string;
  max_per_parent: number;
};

export type FieldValidation = {
  field: string;
  min_length?: number | null;
  max_length?: number | null;
  pattern?: string | null;
  ge?: number | null;
  le?: number | null;
  format?: string | null;
};

export type RowLevelConfig = {
  column: string;
  claim: string;
  required: boolean;
};

export type SoftDeleteConfig = {
  column: string;
};

export type DeprecationConfig = {
  deprecated: boolean;
  sunset?: string | null;
  link?: string | null;
  successor?: string | null;
};

export type SqlParam = {
  name: string;
  type: "string" | "int" | "float" | "bool";
  required?: boolean;
  default?: string | number | boolean | null;
  description?: string | null;
};

export type WebhookDraft = {
  url: string;
  events: string[];
  secret?: string | null;
  timeout_seconds?: number;
};

export type JwtConfigDraft = {
  issuer: string;
  audience: string;
  algorithm: string;
  access_ttl_minutes: number;
  refresh_ttl_days: number;
};

export type RbacRoleDraft = {
  role: string;
  endpoints: Record<string, string[]>;
};

export const WEBHOOK_EVENTS = ["create", "update", "delete", "bulk_create"] as const;

export const VALIDATION_FORMATS = ["email", "uuid", "uri"] as const;

export type AggregateMetricDraft = {
  name: string;
  op: "count" | "sum" | "avg" | "min" | "max";
  field?: string | null;
};

export type AggregateDraft = {
  table: string;
  schema?: string;
  group_by: string[];
  metrics: AggregateMetricDraft[];
};

export type EndpointDraft = {
  name: string;
  path: string;
  table: string;
  schema: string;
  sql?: string | null;
  sql_params?: SqlParam[];
  aggregate?: AggregateDraft | null;
  methods: string[];
  primary_key: string;
  fields: string[];
  writable_fields?: string[];
  filters: string[];
  filter_operators?: string[];
  search_param?: string | null;
  sortable: string[];
  pagination?: {
    enabled: boolean;
    mode: "cursor" | "offset";
    default_limit: number;
    max_limit: number;
  };
  relations?: RelationDraft[];
  roles?: string[];
  row_level?: RowLevelConfig | null;
  soft_delete?: SoftDeleteConfig | null;
  etag_field?: string | null;
  validations?: FieldValidation[];
  bulk_enabled?: boolean;
  async_writes?: boolean;
  deprecation?: DeprecationConfig;
  description?: string;
  allow_sensitive?: boolean;
  csv_export?: boolean;
  ndjson_export?: boolean;
  parquet_export?: boolean;
};

export type DatabaseDriver = "postgres" | "duckdb";

export type ApiSpecDraft = {
  database: { url: string; driver?: DatabaseDriver };
  app: {
    title: string;
    version: string;
    description: string;
    read_only: boolean;
    auth: "none" | "api_key" | "jwt";
    api_prefix?: string;
    legacy_api_prefix?: string | null;
    cache?: { enabled: boolean; ttl_seconds: number };
    idempotency?: { enabled: boolean; required_for_writes?: boolean; ttl_seconds?: number };
    rate_limit: { enabled: boolean; requests_per_minute: number };
    audit_enabled?: boolean;
    compression?: boolean;
    tracing?: boolean;
    ip_allowlist?: string[];
    webhooks?: WebhookDraft[];
    jwt?: JwtConfigDraft;
    environment?: string;
    deprecation?: DeprecationConfig;
    rbac?: RbacRoleDraft[];
  };
  endpoints: EndpointDraft[];
};

export type ValidateResult = {
  valid: boolean;
  errors: string[];
  warnings: string[];
  endpoint_count: number;
};

export type SpecListItem = {
  name: string;
  path: string;
  updated_at?: number;
  title?: string;
  version?: string;
  endpoint_count?: number;
  auth?: string;
  api_prefix?: string;
  read_only?: boolean;
};

export type ActiveInfo = {
  active: boolean;
  name?: string | null;
  apis?: string[];
  summary?: {
    title: string;
    version: string;
    endpoint_count: number;
    auth: string;
    api_prefix: string;
    read_only: boolean;
    endpoints: { name: string; path: string; methods: string[] }[];
  } | null;
};

export type ActiveApiMount = {
  name: string;
  primary: boolean;
  title: string;
  version: string;
  endpoint_count: number;
  mount: string;
  primary_mount?: string | null;
};

export type StudioHealth = {
  status: string;
  plane?: string;
  oidc?: boolean;
  job_queue?: boolean;
  multi_active?: boolean;
  graphql?: boolean;
  active_apis?: number;
  experimental?: string[];
};

export type OpenApiDiff = {
  breaking: boolean;
  summary: { added: number; removed: number; updated: number };
  changes: Array<{
    path: string;
    method: string;
    type: "NEW" | "UPDATE" | "DELETE";
    added_fields?: string[];
    removed_fields?: string[];
    breaking?: boolean;
  }>;
};

export const ALL_FILTER_OPS = [
  "eq",
  "ne",
  "gt",
  "gte",
  "lt",
  "lte",
  "contains",
  "startswith",
  "in",
  "search",
] as const;

export const ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;
