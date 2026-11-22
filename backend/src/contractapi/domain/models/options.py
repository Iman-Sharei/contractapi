"""Building blocks of an endpoint/app contract: enums and option models (pagination, relations, auth, webhooks…)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from contractapi.domain.sensitive import assert_fields_safe


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
    # Optional: hide child rows where this column is set (e.g. deleted_at).
    soft_delete_column: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")

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


_LOCAL_SUFFIXES = (".localhost", ".internal", ".local", ".test")
_CLAIM_PATH = re.compile(r"^[A-Za-z0-9_:\-]+(\.[A-Za-z0-9_:\-]+)*$")


def _check_login_url(label: str, url: str) -> str:
    """https, except for local/test hosts (plain http would let anyone swap the signing keys)."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"} or "." not in host or host.endswith(_LOCAL_SUFFIXES)
    if parsed.scheme not in ("https", "http") or not host:
        raise ValueError(f"{label} must be a web address like https://login.example.com/realms/main")
    if parsed.scheme == "http" and not local:
        raise ValueError(f"{label} must use https:// (only local test servers may use http://)")
    return url.strip()  # kept as typed: the token's "iss" must match it exactly


class JwtConfig(BaseModel):
    """Login tokens (JWT). provider "contractapi": signed by this server with JWT_SECRET (testing,
    or your own backend). provider "oidc": issued by your company login (Keycloak, Azure AD,
    Okta, Google…) and checked against its public signing keys (JWKS)."""

    provider: Literal["contractapi", "oidc"] = "contractapi"
    issuer: str = "contractapi"
    audience: str = "contractapi-clients"
    algorithm: str = "HS256"
    access_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_ttl_days: int = Field(default=7, ge=1, le=90)
    # Secret comes from env JWT_SECRET — never store in YAML.
    jwks_url: str | None = Field(default=None, description="Only if the login server does not publish discovery")
    roles_claim: str = Field(default="roles", description="Where roles are in the token, e.g. realm_access.roles")

    @model_validator(mode="after")
    def check_provider(self) -> JwtConfig:
        if not _CLAIM_PATH.match(self.roles_claim):
            raise ValueError(f"roles_claim '{self.roles_claim}' must be a claim name or path like realm_access.roles")
        if self.provider == "contractapi":
            if self.algorithm not in {"HS256", "HS384", "HS512"}:
                raise ValueError(
                    f"algorithm '{self.algorithm}' needs keys from a login server: set provider: oidc "
                    "and its issuer address (this server signs with HS256/HS384/HS512 only)"
                )
            return self
        self.issuer = _check_login_url("The login server address (issuer)", self.issuer)
        if self.jwks_url:
            self.jwks_url = _check_login_url("jwks_url", self.jwks_url)
        if not self.audience.strip():
            raise ValueError("Set the audience your login server puts in tokens (client ID or API identifier)")
        return self


class RowLevelConfig(BaseModel):
    """BOLA protection: force column = JWT claim (or fixed value)."""

    column: str
    claim: str = "sub"
    # If true, missing claim → 403; if false, skip filter (dev only).
    required: bool = True


class SoftDeleteConfig(BaseModel):
    column: str = "deleted_at"
    # On DELETE set to NOW(); list/detail exclude non-null.
    # POST /{path}/{id}/restore brings a deleted row back (needs DELETE allowed).
    restore: bool = False
    # A create that clashes on a unique value with a deleted row revives that row instead of 409.
    reuse_deleted: bool = False


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
    url: str = Field(pattern=r"^https?://[^\s/]+", description="http(s) URL of the receiver")
    events: list[str] = Field(
        default_factory=lambda: ["create", "update", "delete", "bulk_create"],
    )
    secret: str | None = None  # HMAC-SHA256 header X-Contractapi-Signature
    timeout_seconds: float = Field(default=3.0, ge=0.5, le=30)
