"""Studio use-cases: introspect, validate, activate spec."""

from __future__ import annotations

from threading import Lock
from typing import Any

from pydantic import ValidationError

from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, parse_spec
from contractapi.domain.sensitive import find_sensitive_columns
from contractapi.infrastructure.db.introspect import introspect_schema, missing_columns


class SpecStore:
    """
    Process-local active specifications.

    - `active` / `active_name`: primary API served under `/data` (backward compatible).
    - `all()`: multi-active map served under `/apis/{name}` (OSS multi-tenant MVP).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._specs: dict[str, ApiSpec] = {}
        self._primary: str | None = None

    @property
    def active(self) -> ApiSpec | None:
        with self._lock:
            if self._primary is None:
                return None
            return self._specs.get(self._primary)

    @property
    def active_name(self) -> str | None:
        with self._lock:
            return self._primary

    def get(self, name: str) -> ApiSpec | None:
        with self._lock:
            return self._specs.get(name)

    def all(self) -> dict[str, ApiSpec]:
        with self._lock:
            return dict(self._specs)

    def set(self, spec: ApiSpec, name: str | None = None, *, primary: bool = True) -> str:
        key = (name or "_default").strip() or "_default"
        with self._lock:
            self._specs[key] = spec
            if primary or self._primary is None:
                self._primary = key
        self._persist()
        return key

    def remove(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._specs.clear()
                self._primary = None
            else:
                self._specs.pop(name, None)
                if self._primary == name:
                    self._primary = next(iter(self._specs), None)
        self._persist()

    def clear(self) -> None:
        self.remove(None)

    def _persist(self) -> None:
        try:
            from contractapi.infrastructure.runtime_store import clear_active, save_active

            with self._lock:
                if not self._specs:
                    clear_active()
                    return
                specs = {
                    n: s.model_dump(by_alias=True, mode="json") for n, s in self._specs.items()
                }
                primary = self._primary
            save_active(primary, specs)
        except Exception:  # noqa: BLE001
            pass

    def revision(self) -> tuple[str | None, tuple[tuple[str, int], ...]]:
        """Cache-bust key for ASGI mounts: primary + (name, id(spec)) pairs."""
        with self._lock:
            items = tuple(sorted((n, id(s)) for n, s in self._specs.items()))
            return self._primary, items


spec_store = SpecStore()


def _sql_param_placeholder(type_name: str) -> Any:
    if type_name == "int":
        return 0
    if type_name == "float":
        return 0.0
    if type_name == "bool":
        return False
    return ""


def introspect(database_url: str, schema: str = "public") -> list[dict[str, Any]]:
    try:
        tables = introspect_schema(database_url, schema=schema)
    except Exception as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/database-unreachable",
            title="Database unreachable",
            status=400,
            detail=str(exc),
        ) from exc
    return [t.to_dict() for t in tables]


def validate_spec_payload(raw: dict[str, Any], *, check_db: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    spec: ApiSpec | None = None
    try:
        spec = parse_spec(raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            errors.append(f"{loc}: {err.get('msg')}")
        return {"valid": False, "errors": errors, "warnings": warnings, "spec": None}

    if check_db and spec is not None:
        try:
            from contractapi.domain.models.spec import DatabaseDriver

            if spec.database.driver == DatabaseDriver.DUCKDB:
                warnings.append(
                    "DuckDB driver: Postgres introspect skipped; ensure columns match the SQL/file schema."
                )
            else:
                url = spec.database.url
                for ep in spec.endpoints:
                    if ep.is_sql:
                        continue
                    try:
                        missing = missing_columns(url, ep.table, ep.schema_name, ep.fields)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(
                            f"Endpoint '{ep.name}': could not introspect table '{ep.table}': {exc}"
                        )
                        continue
                    if missing:
                        errors.append(
                            f"Endpoint '{ep.name}': missing columns: {', '.join(missing)}"
                        )
                    flagged = find_sensitive_columns(ep.fields)
                    if flagged and not ep.allow_sensitive:
                        warnings.append(
                            f"Endpoint '{ep.name}': fields look sensitive: {', '.join(flagged)}"
                        )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Database check skipped: {exc}")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "endpoint_count": len(spec.endpoints) if spec else 0,
        "spec": spec.model_dump(by_alias=True, mode="json") if spec else None,
    }


def activate_spec(
    raw: dict[str, Any],
    *,
    name: str | None = None,
    primary: bool = True,
) -> ApiSpec:
    result = validate_spec_payload(raw, check_db=True)
    if not result["valid"]:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-spec",
            title="Invalid specification",
            status=400,
            detail="Specification failed validation.",
            extensions={"errors": result["errors"], "warnings": result["warnings"]},
        )
    spec = parse_spec(raw)
    spec_store.set(spec, name=name, primary=primary)
    return spec
