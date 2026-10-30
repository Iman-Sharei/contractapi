"""Runtime settings — 12-factor style (env / .env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "dataapi"
    environment: str = "development"
    debug: bool = False

    # Studio control-plane
    studio_host: str = "0.0.0.0"
    studio_port: int = 8000
    studio_api_key: str = Field(
        default="dev-studio-key-change-me",
        description="Required on studio routes via X-API-Key (OWASP: protect management plane).",
    )
    cors_origins: str = "http://localhost:3000"

    # Data-plane defaults
    default_rate_limit_per_minute: int = 120
    max_request_body_bytes: int = 1_048_576  # 1 MiB
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_statement_timeout_ms: int = 10_000

    # Security
    force_https_headers: bool = True
    data_api_keys: str = Field(
        default="",
        description="Comma-separated API keys for served data APIs. Empty = open (dev only).",
    )
    jwt_secret: str = Field(
        default="dev-jwt-secret-change-me-please-32chars",
        description="HS256 secret for data-plane JWT auth.",
    )
    specs_dir: str = Field(
        default="./specs",
        description="Directory for persisted YAML API specifications.",
    )
    redis_url: str = Field(
        default="",
        description="Optional Redis URL for shared cache/idempotency/token revoke/job queue.",
    )
    job_queue_enabled: bool = Field(
        default=False,
        description="When true and redis_url is set, async writes use a Redis list workers can BRPOP.",
    )
    job_queue_key: str = Field(default="dataapi:jobs:queue")
    audit_log_path: str = Field(
        default="./logs/audit.jsonl",
        description="Append-only audit log path.",
    )
    otel_exporter_endpoint: str = Field(
        default="",
        description="Optional OTLP HTTP JSON endpoint for span export.",
    )
    # Studio OIDC (optional — keep X-API-Key as break-glass)
    studio_oidc_issuer: str = Field(
        default="",
        description="OIDC issuer URL (e.g. https://keycloak.example/realms/dataapi). Empty = disabled.",
    )
    studio_oidc_audience: str = Field(
        default="",
        description="Expected aud claim; empty accepts any audience from issuer.",
    )
    studio_oidc_jwks_url: str = Field(
        default="",
        description="JWKS URL override; default = {issuer}/.well-known/openid-configuration → jwks_uri.",
    )
    studio_oidc_email_allowlist: str = Field(
        default="",
        description="Comma-separated emails allowed into Studio; empty = any valid token.",
    )
    # Comma list: graphql,duckdb,parquet,oidc,queue,multi_active — or "all"
    experimental: str = Field(
        default="all",
        description="Experimental feature gate for Beta. Use empty to disable optional surfaces.",
    )
    # Optional YAML path activated on boot (in addition to .runtime/active.json)
    boot_spec: str = Field(
        default="",
        description="Path to YAML activated as primary on startup.",
        validation_alias=AliasChoices("boot_spec", "DATAAPI_BOOT_SPEC"),
    )
    restore_active_on_boot: bool = Field(
        default=True,
        description="Reload SPECS_DIR/.runtime/active.json on process start.",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def data_api_key_set(self) -> set[str]:
        return {k.strip() for k in self.data_api_keys.split(",") if k.strip()}

    @property
    def experimental_set(self) -> set[str]:
        raw = self.experimental.strip().lower()
        if not raw:
            return set()
        if raw == "all":
            return {"graphql", "duckdb", "parquet", "oidc", "queue", "multi_active"}
        return {p.strip() for p in raw.split(",") if p.strip()}

    def experimental_enabled(self, feature: str) -> bool:
        return feature.lower() in self.experimental_set


@lru_cache
def get_settings() -> Settings:
    return Settings()
