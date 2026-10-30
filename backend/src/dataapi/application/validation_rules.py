"""Apply FieldValidation rules from the API spec."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from dataapi.core.errors import AppError
from dataapi.domain.models.spec import EndpointSpec, FieldValidation


def validate_payload(endpoint: EndpointSpec, payload: dict[str, Any]) -> None:
    rules = {r.field: r for r in endpoint.validations}
    errors: list[str] = []
    for field, value in payload.items():
        rule = rules.get(field)
        if not rule or value is None:
            continue
        err = _check(rule, value)
        if err:
            errors.append(f"{field}: {err}")
    if errors:
        raise AppError(
            type_="https://dataapi.dev/problems/validation-error",
            title="Validation failed",
            status=422,
            detail="One or more fields failed validation rules.",
            extensions={"errors": errors},
        )


def _check(rule: FieldValidation, value: Any) -> str | None:
    if isinstance(value, str):
        if rule.min_length is not None and len(value) < rule.min_length:
            return f"min_length {rule.min_length}"
        if rule.max_length is not None and len(value) > rule.max_length:
            return f"max_length {rule.max_length}"
        if rule.pattern and not re.search(rule.pattern, value):
            return "pattern mismatch"
        if rule.format == "email" and ("@" not in value or "." not in value.split("@")[-1]):
            return "invalid email"
        if rule.format == "uuid":
            try:
                UUID(value)
            except Exception:
                return "invalid uuid"
        if rule.format == "uri" and not (value.startswith("http://") or value.startswith("https://")):
            return "invalid uri"
    if isinstance(value, (int, float)):
        if rule.ge is not None and value < rule.ge:
            return f"must be >= {rule.ge}"
        if rule.le is not None and value > rule.le:
            return f"must be <= {rule.le}"
    return None
