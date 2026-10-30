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


class SqlPreviewRequest(BaseModel):
    database_url: str = Field(min_length=1)
    sql: str = Field(min_length=1)


class DumpYamlRequest(BaseModel):
    spec: dict[str, Any]
