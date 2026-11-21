"""EndpointSpec: one published resource of the contract and its validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from contractapi.domain.models.aggregate import (
    AggregateConfig,
    compile_aggregate_sql,
    derived_aggregate_fields,
)
from contractapi.domain.models.options import (
    DeprecationConfig,
    FieldValidation,
    HttpMethod,
    PaginationConfig,
    PaginationMode,
    RelationSpec,
    RowLevelConfig,
    SoftDeleteConfig,
    SqlParam,
)
from contractapi.domain.models.rules import (
    PATH_RE,
    _assert_safe_select,
    suggest_path,
)
from contractapi.domain.models.write_options import TimestampsConfig, check_write_rules
from contractapi.domain.sensitive import WRITE_METHODS, assert_fields_safe


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
    # Declarative GROUP BY metrics — compiled to sql (mutually exclusive with raw sql/writes).
    aggregate: AggregateConfig | None = None
    methods: list[HttpMethod] = Field(default_factory=lambda: [HttpMethod.GET])
    fields: list[str] = Field(default_factory=list)
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
    # true: a bulk create stores all rows or none (one transaction); false: per-row (HTTP 207).
    bulk_atomic: bool = False
    timestamps: TimestampsConfig | None = None
    # Values used on create when the client leaves the column out.
    defaults: dict[str, Any] = Field(default_factory=dict)
    # Values the API always writes (create and update); clients cannot change them.
    fixed_values: dict[str, Any] = Field(default_factory=dict)
    # one_to_many relations whose children can be created with the parent, in one transaction.
    nested_writes: list[str] = Field(default_factory=list)
    async_writes: bool = False
    deprecation: DeprecationConfig = Field(default_factory=DeprecationConfig)
    description: str | None = None
    allow_sensitive: bool = False
    # When true, list endpoints also honor Accept: text/csv | application/x-ndjson | parquet
    csv_export: bool = True
    ndjson_export: bool = True
    parquet_export: bool = False  # GA; requires optional extra: pip install contractapi[parquet]

    model_config = {"populate_by_name": True}

    @property
    def is_sql(self) -> bool:
        return bool(self.sql and self.sql.strip())

    @property
    def is_aggregate(self) -> bool:
        return self.aggregate is not None

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            value = "/" + value
        value = value.rstrip("/")
        if not PATH_RE.match(value):
            raise ValueError(
                f"URL path '{value or '/'}' is not valid. Use lowercase letters, digits, "
                f"'-' or '_' separated by '/', e.g. '{suggest_path(value) if value else '/items'}'."
            )
        return value

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
        if self.aggregate is not None:
            # Always recompile from DSL (dump_spec may also include expanded sql).
            fields = derived_aggregate_fields(self.aggregate)
            object.__setattr__(self, "sql", compile_aggregate_sql(self.aggregate))
            object.__setattr__(self, "fields", fields)
            object.__setattr__(self, "primary_key", fields[0])
            object.__setattr__(
                self,
                "sortable",
                list(self.aggregate.group_by) or fields[:1],
            )
            if not self.filters:
                object.__setattr__(self, "filters", list(self.aggregate.group_by))
            object.__setattr__(self, "table", self.aggregate.table)
            object.__setattr__(self, "schema_name", self.aggregate.schema_name)
            object.__setattr__(self, "methods", [HttpMethod.GET])
            object.__setattr__(self, "writable_fields", [])
            object.__setattr__(self, "relations", [])
            if self.pagination.mode.value == "cursor":
                # Aggregates are unordered sets — prefer offset paging.
                object.__setattr__(
                    self,
                    "pagination",
                    self.pagination.model_copy(update={"mode": PaginationMode.OFFSET}),
                )

        if not self.fields:
            raise ValueError(f"Endpoint '{self.name}': fields must not be empty")

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
            raise ValueError(
                f"Endpoint '{self.name}': table is required unless sql or aggregate is set"
            )

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
        check_write_rules(self)
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
