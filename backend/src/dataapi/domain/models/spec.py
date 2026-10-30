"""API specification — source of truth (not the database schema)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from dataapi.domain.sensitive import WRITE_METHODS, assert_fields_safe


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class AuthMode(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    JWT = "jwt"


class PaginationMode(str, Enum):
    OFFSET = "offset"
    CURSOR = "cursor"


class RelationType(str, Enum):
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"


class PaginationConfig(BaseModel):
    enabled: bool = True
    mode: PaginationMode = PaginationMode.CURSOR
    default_limit: int = Field(default=20, ge=1, le=1000)
    max_limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def check_limits(self) -> PaginationConfig:
        if self.default_limit > self.max_limit:
            raise ValueError("default_limit cannot exceed max_limit")
        return self


class RateLimitConfig(BaseModel):
    enabled: bool = True
    requests_per_minute: int = Field(default=120, ge=1, le=10_000)


class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_seconds: int = Field(default=30, ge=1, le=3600)
    # GET list/detail only; invalidated automatically on writes to same endpoint.


class IdempotencyConfig(BaseModel):
    enabled: bool = True
    ttl_seconds: int = Field(default=86_400, ge=60, le=604_800)
    required_for_writes: bool = False  # if true, missing Idempotency-Key → 400


class RelationSpec(BaseModel):
    """Nested resource loaded in batch (anti N+1 via WHERE fk IN (...))."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    table: str
    schema_name: str = Field(default="public", alias="schema")
    type: RelationType = RelationType.ONE_TO_MANY
    local_key: str = Field(description="Column on parent table")
    foreign_key: str = Field(description="Column on related table")
    fields: list[str] = Field(min_length=1)
    primary_key: str = "id"
    max_per_parent: int = Field(default=50, ge=1, le=500)
    allow_sensitive: bool = False

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_relation(self) -> RelationSpec:
        assert_fields_safe(self.fields, allow_sensitive=self.allow_sensitive)
        if self.foreign_key not in self.fields and self.type == RelationType.ONE_TO_MANY:
            # FK needed for grouping; auto-include for query, may hide from response later
            pass
        return self


class RolePermissions(BaseModel):
    """Per-endpoint field visibility for a role (OWASP API3 property-level authz)."""

    role: str = Field(min_length=1)
    endpoints: dict[str, list[str]] = Field(
        default_factory=dict,
        description="endpoint_name → allowlisted response fields",
    )


class JwtConfig(BaseModel):
    issuer: str = "dataapi"
    audience: str = "dataapi-clients"
    algorithm: str = "HS256"
    access_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_ttl_days: int = Field(default=7, ge=1, le=90)
    # Secret comes from env JWT_SECRET — never store in YAML.


class RowLevelConfig(BaseModel):
    """BOLA protection: force column = JWT claim (or fixed value)."""

    column: str
    claim: str = "sub"
    # If true, missing claim → 403; if false, skip filter (dev only).
    required: bool = True


class SoftDeleteConfig(BaseModel):
    column: str = "deleted_at"
    # On DELETE set to NOW(); list/detail exclude non-null.


class DeprecationConfig(BaseModel):
    deprecated: bool = False
    sunset: str | None = None  # ISO date YYYY-MM-DD
    link: str | None = None
    successor: str | None = None  # e.g. /v2/customers


class FieldValidation(BaseModel):
    """Optional stricter validation beyond DB nullability."""

    field: str
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    ge: float | None = None
    le: float | None = None
    format: str | None = None  # email | uuid | uri


class SqlParam(BaseModel):
    """Named bind param for EndpointSpec.sql, exposed as query string."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: str = "string"  # string | int | float | bool
    required: bool = False
    default: Any = None
    description: str | None = None


class WebhookConfig(BaseModel):
    url: str
    events: list[str] = Field(
        default_factory=lambda: ["create", "update", "delete", "bulk_create"],
    )
    secret: str | None = None  # HMAC-SHA256 header X-Dataapi-Signature
    timeout_seconds: float = Field(default=3.0, ge=0.5, le=30)


class EndpointSpec(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    path: str
    # Physical table/view name. Optional when `sql` is set (custom SELECT).
    table: str = Field(default="")
    schema_name: str = Field(default="public", alias="schema")
    # Custom read-only SELECT (aggregations, joins, metrics). Mutually exclusive with writes.
    sql: str | None = Field(
        default=None,
        description="Optional SELECT used as a subquery source instead of a base table.",
    )
    methods: list[HttpMethod] = Field(default_factory=lambda: [HttpMethod.GET])
    fields: list[str] = Field(min_length=1)
    writable_fields: list[str] = Field(default_factory=list)
    primary_key: str = "id"
    filters: list[str] = Field(default_factory=list)
    # Allowed ops: eq, ne, gt, gte, lt, lte, contains, startswith, in, search (FTS/ilike)
    filter_operators: list[str] = Field(
        default_factory=lambda: [
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
        ]
    )
    # Global ?q= across filter fields (OR of contains/search)
    search_param: str | None = Field(default="q", description="Set null to disable ?q=")
    sql_params: list[SqlParam] = Field(default_factory=list)
    sortable: list[str] = Field(default_factory=list)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    relations: list[RelationSpec] = Field(default_factory=list)
    roles: list[str] = Field(
        default_factory=list,
        description="If non-empty, JWT must include at least one of these roles.",
    )
    row_level: RowLevelConfig | None = None
    soft_delete: SoftDeleteConfig | None = None
    etag_field: str | None = Field(
        default=None,
        description="Column used for ETag/If-Match (e.g. version or updated_at).",
    )
    validations: list[FieldValidation] = Field(default_factory=list)
    bulk_enabled: bool = True
    async_writes: bool = False
    deprecation: DeprecationConfig = Field(default_factory=DeprecationConfig)
    description: str | None = None
    allow_sensitive: bool = False
    # When true, list endpoints also honor Accept: text/csv | application/x-ndjson | parquet
    csv_export: bool = True
    ndjson_export: bool = True
    parquet_export: bool = False  # requires optional extra: pip install dataapi[parquet]

    model_config = {"populate_by_name": True}

    @property
    def is_sql(self) -> bool:
        return bool(self.sql and self.sql.strip())

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            value = "/" + value
        if "//" in value:
            raise ValueError("path must not contain empty segments")
        return value.rstrip("/") or "/"

    @field_validator("fields", "filters", "sortable", "writable_fields", "roles")
    @classmethod
    def unique_names(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    @model_validator(mode="after")
    def validate_contract(self) -> EndpointSpec:
        assert_fields_safe(self.fields, allow_sensitive=self.allow_sensitive)
        if self.is_sql:
            _assert_safe_select(self.sql or "", endpoint_name=self.name)
            if self.allows_writes:
                raise ValueError(f"Endpoint '{self.name}': SQL sources are read-only (GET only)")
            if self.relations:
                raise ValueError(f"Endpoint '{self.name}': SQL sources cannot declare relations")
            if self.row_level or self.soft_delete:
                raise ValueError(
                    f"Endpoint '{self.name}': row_level/soft_delete are table-only features"
                )
            if not self.table:
                object.__setattr__(self, "table", "_sql")
            # Force GET-only
            object.__setattr__(self, "methods", [HttpMethod.GET])
            object.__setattr__(self, "writable_fields", [])
        elif not self.table:
            raise ValueError(f"Endpoint '{self.name}': table is required unless sql is set")

        if self.primary_key not in self.fields:
            raise ValueError(
                f"Endpoint '{self.name}': primary_key '{self.primary_key}' must be in fields"
            )
        field_set = set(self.fields)
        for col in self.filters + self.sortable + self.writable_fields:
            if col not in field_set:
                raise ValueError(
                    f"Endpoint '{self.name}': '{col}' must be listed in fields"
                )
        if self.etag_field and self.etag_field not in field_set:
            raise ValueError(
                f"Endpoint '{self.name}': etag_field '{self.etag_field}' must be in fields"
            )
        allowed_ops = {
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
        }
        bad_ops = set(self.filter_operators) - allowed_ops
        if bad_ops:
            raise ValueError(f"Endpoint '{self.name}': unknown filter operators: {sorted(bad_ops)}")
        if self.sql_params and not self.is_sql:
            raise ValueError(f"Endpoint '{self.name}': sql_params require sql")
        param_names = [p.name for p in self.sql_params]
        if len(param_names) != len(set(param_names)):
            raise ValueError(f"Endpoint '{self.name}': duplicate sql_params")
        for rule in self.validations:
            if rule.field not in field_set and rule.field not in set(self.writable_fields):
                raise ValueError(
                    f"Endpoint '{self.name}': validation field '{rule.field}' unknown"
                )
        for rel in self.relations:
            if rel.local_key not in field_set:
                raise ValueError(
                    f"Endpoint '{self.name}': relation '{rel.name}' local_key "
                    f"'{rel.local_key}' must be in fields"
                )
            if rel.name in field_set:
                raise ValueError(
                    f"Endpoint '{self.name}': relation name '{rel.name}' clashes with a field"
                )
        if self.allows_writes and not self.writable_fields:
            self.writable_fields = [f for f in self.fields if f != self.primary_key]
        if (
            self.pagination.enabled
            and self.pagination.mode == PaginationMode.CURSOR
            and self.primary_key not in self.sortable
        ):
            self.sortable = [self.primary_key, *self.sortable]
        return self

    @property
    def allows_writes(self) -> bool:
        return any(m.value in WRITE_METHODS for m in self.methods)


_FORBIDDEN_SQL = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "call",
    "execute",
    "into",
)


def _assert_safe_select(sql: str, *, endpoint_name: str) -> None:
    import re

    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError(f"Endpoint '{endpoint_name}': sql is empty")
    if ";" in cleaned:
        raise ValueError(f"Endpoint '{endpoint_name}': sql must be a single statement")
    lower = cleaned.lower()
    lines = [ln for ln in lower.splitlines() if not ln.strip().startswith("--")]
    compact = " ".join(lines).strip()
    if not compact.startswith("select") and not compact.startswith("with"):
        raise ValueError(f"Endpoint '{endpoint_name}': sql must start with SELECT or WITH")
    for token in _FORBIDDEN_SQL:
        if re.search(rf"\b{re.escape(token)}\b", compact):
            raise ValueError(
                f"Endpoint '{endpoint_name}': sql contains forbidden keyword '{token}'"
            )


class DatabaseDriver(str, Enum):
    POSTGRES = "postgres"
    DUCKDB = "duckdb"


class DatabaseConfig(BaseModel):
    url: str = Field(min_length=1)
    # postgres (default) | duckdb — warehouse/local analytics MVP
    driver: DatabaseDriver = DatabaseDriver.POSTGRES


class AppConfig(BaseModel):
    title: str = "dataapi"
    version: str = "0.1.0"
    description: str = "Generated by dataapi from an explicit API specification."
    read_only: bool = True
    auth: AuthMode = AuthMode.API_KEY
    jwt: JwtConfig = Field(default_factory=JwtConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    idempotency: IdempotencyConfig = Field(default_factory=IdempotencyConfig)
    # API versioning prefix, e.g. /v1 — empty string disables prefix.
    api_prefix: str = "/v1"
    # Optional second prefix served from same app (migration window).
    legacy_api_prefix: str | None = None
    deprecation: DeprecationConfig = Field(default_factory=DeprecationConfig)
    audit_enabled: bool = True
    compression: bool = True
    tracing: bool = True
    # Comma-separated CIDRs/IPs; empty = allow all
    ip_allowlist: list[str] = Field(default_factory=list)
    webhooks: list[WebhookConfig] = Field(default_factory=list)
    # Environment label for promote workflows: development|staging|production
    environment: str = "development"
    rbac: list[RolePermissions] = Field(default_factory=list)

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        if not value.startswith("/"):
            value = "/" + value
        return value.rstrip("/")

    @field_validator("legacy_api_prefix")
    @classmethod
    def normalize_legacy_prefix(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        value = value.strip()
        if not value.startswith("/"):
            value = "/" + value
        return value.rstrip("/")


class ApiSpec(BaseModel):
    database: DatabaseConfig
    app: AppConfig = Field(default_factory=AppConfig)
    endpoints: list[EndpointSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_invariants(self) -> ApiSpec:
        paths: set[str] = set()
        names: set[str] = set()
        for ep in self.endpoints:
            if ep.path in paths:
                raise ValueError(f"Duplicate endpoint path: {ep.path}")
            if ep.name in names:
                raise ValueError(f"Duplicate endpoint name: {ep.name}")
            paths.add(ep.path)
            names.add(ep.name)
            if self.app.read_only and ep.allows_writes:
                raise ValueError(
                    f"Endpoint '{ep.name}' declares write methods but app.read_only=true"
                )
        for role in self.app.rbac:
            for ep_name, fields in role.endpoints.items():
                if ep_name not in names:
                    raise ValueError(f"RBAC role '{role.role}' references unknown endpoint '{ep_name}'")
                ep = next(e for e in self.endpoints if e.name == ep_name)
                unknown = set(fields) - set(ep.fields)
                if unknown:
                    raise ValueError(
                        f"RBAC role '{role.role}' endpoint '{ep_name}' has unknown fields: "
                        + ", ".join(sorted(unknown))
                    )
        return self

    def rbac_fields_for(self, endpoint_name: str, roles: list[str]) -> list[str] | None:
        """Return intersection of allowed fields for roles, or None if RBAC unused."""
        if not self.app.rbac:
            return None
        allowed: set[str] | None = None
        for role_perm in self.app.rbac:
            if role_perm.role not in roles:
                continue
            fields = role_perm.endpoints.get(endpoint_name)
            if fields is None:
                continue
            allowed = set(fields) if allowed is None else allowed & set(fields)
        return sorted(allowed) if allowed is not None else []


def load_spec(path: str | Path) -> ApiSpec:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ApiSpec.model_validate(data)


def dump_spec(spec: ApiSpec) -> str:
    return yaml.safe_dump(
        spec.model_dump(by_alias=True, mode="json"),
        sort_keys=False,
        allow_unicode=True,
    )


def parse_spec(raw: dict[str, Any] | str) -> ApiSpec:
    if isinstance(raw, str):
        data = yaml.safe_load(raw) or {}
    else:
        data = raw
    return ApiSpec.model_validate(data)
