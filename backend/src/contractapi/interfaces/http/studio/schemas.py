"""Studio control-plane request/response DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntrospectRequest(BaseModel):
    database_url: str = Field(min_length=1)
    schema_name: str = Field(default="public", alias="schema")

    model_config = {"populate_by_name": True}


class ValidateSpecRequest(BaseModel):
    spec: dict[str, Any]
    check_db: bool = True
    name: str | None = None  # optional saved-spec name when activating


class ValidateSpecResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    endpoint_count: int = 0


class OpenApiPreviewRequest(BaseModel):
    spec: dict[str, Any]


class ServeInfoResponse(BaseModel):
    message: str
    name: str | None = None
    mount: str | None = None
    primary: bool = True
    docs_path: str = "/data/docs"
    openapi_path: str = "/data/openapi.json"


class SaveSpecRequest(BaseModel):
    name: str
    spec: dict[str, Any]


class DiffOpenApiRequest(BaseModel):
    before: dict[str, Any]
    after: dict[str, Any]


class IssueTokenRequest(BaseModel):
    sub: str = "demo-user"
    roles: list[str] = Field(default_factory=lambda: ["analyst"])
    expires_minutes: int = Field(default=60, ge=1, le=24 * 60)
    # Active API whose jwt issuer/audience/algorithm the token targets (default: primary /data).
    api: str | None = None
    # Extra claims for testing row-level security (e.g. {"tenant_id": "acme"}).
    # Reserved claims (sub, roles, exp, iss, aud, …) are ignored.
    claims: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SqlPreviewRequest(BaseModel):
    database_url: str = Field(min_length=1)
    sql: str = Field(min_length=1)
    driver: str = Field(
        default="postgres",
        description="postgres | mysql | sqlserver | duckdb | snowflake | bigquery",
    )


class DumpYamlRequest(BaseModel):
    spec: dict[str, Any]


class EndpointDatabaseChange(BaseModel):
    name: str
    table: str | None = None
    status: str = Field(description="ok | changed | missing_table | skipped")
    missing: list[str] = Field(default_factory=list)
    new_columns: list[str] = Field(default_factory=list, description="Not shared yet; sensitive columns left out")
    detail: str | None = None


class DatabaseChangesResponse(BaseModel):
    ok: bool
    endpoints: list[EndpointDatabaseChange]


class ProblemDetails(BaseModel):
    """RFC 9457 error body (application/problem+json)."""

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
