"""Files a data team hands to the developers who call its API: OpenAPI, Postman, Python client.

All of them point at the API's real address ({PUBLIC_API_BASE}/apis/{name}), carry its auth
(X-API-Key or Bearer token) and list only the operations the contract allows.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from contractapi.core.config import get_settings
from contractapi.domain.models.spec import ApiSpec, AuthMode, EndpointSpec, HttpMethod


def api_base_url(name: str | None) -> str:
    """Where callers reach this API: the named mount, or the primary /data mount."""
    base = get_settings().public_api_base.rstrip("/")
    return f"{base}/apis/{name}" if name else f"{base}/data"


def export_openapi(spec: ApiSpec, name: str | None = None) -> dict[str, Any]:
    from contractapi.application.data_api_builder import create_data_app

    doc = copy.deepcopy(create_data_app(spec).openapi())
    doc["servers"] = [{"url": api_base_url(name), "description": "This API"}]
    return doc


def compare_draft_with_saved(name: str, raw_draft: dict[str, Any]) -> dict[str, Any]:
    """What a draft would change for callers of the saved API (breaking = callers fail)."""
    from contractapi.application.openapi_diff import diff_openapi
    from contractapi.domain.models.spec import parse_spec
    from contractapi.infrastructure.persistence import spec_repo

    if not spec_repo.spec_exists(name):
        return diff_openapi({}, {})  # a new API cannot break anyone
    before = export_openapi(spec_repo.read_spec(name), name)
    after = export_openapi(parse_spec(raw_draft), name)
    return diff_openapi(before, after)


# ---------------------------------------------------------------- operations of one endpoint


def _operations(ep: EndpointSpec, read_only: bool) -> list[tuple[str, str, str]]:
    """(kind, method, path suffix) for every route the contract creates."""
    ops = [("list", "GET", ""), ("get", "GET", "/{id}")] if HttpMethod.GET in ep.methods or ep.is_sql else []
    if read_only or ep.is_sql:
        return ops
    if HttpMethod.POST in ep.methods:
        ops.append(("create", "POST", ""))
        if ep.bulk_enabled:
            ops.append(("bulk_create", "POST", "/bulk"))
    if HttpMethod.PATCH in ep.methods:
        ops.append(("update", "PATCH", "/{id}"))
    if HttpMethod.PUT in ep.methods:
        ops.append(("replace", "PUT", "/{id}"))
    if HttpMethod.DELETE in ep.methods:
        ops.append(("delete", "DELETE", "/{id}"))
        if ep.soft_delete and ep.soft_delete.restore:
            ops.append(("restore", "POST", "/{id}/restore"))
    return ops


def _sample_body(ep: EndpointSpec) -> dict[str, Any]:
    return {f: f"<{f}>" for f in (ep.writable_fields or [f for f in ep.fields if f != ep.primary_key])}


# ---------------------------------------------------------------- Postman


def build_postman_collection(spec: ApiSpec, name: str | None = None) -> dict[str, Any]:
    prefix = spec.app.api_prefix or ""
    folders = []
    for ep in spec.endpoints:
        requests = []
        for kind, method, suffix in _operations(ep, spec.app.read_only):
            path = f"{prefix}{ep.path}{suffix}".replace("{id}", ":id")
            url: dict[str, Any] = {
                "raw": "{{baseUrl}}" + path,
                "host": ["{{baseUrl}}"],
                "path": [p for p in path.strip("/").split("/") if p],
            }
            if ":id" in path:
                url["variable"] = [{"key": "id", "value": "1", "description": f"{ep.primary_key} of the row"}]
            if kind == "list":
                query = [{"key": "limit", "value": str(ep.pagination.default_limit)}]
                query += [{"key": f, "value": "", "disabled": True} for f in ep.filters]
                if ep.search_param and ep.filters:
                    query.append({"key": ep.search_param, "value": "", "disabled": True})
                url["query"] = query
            request: dict[str, Any] = {"method": method, "header": [], "url": url,
                                       "description": ep.description or ""}
            if kind in ("create", "update", "replace", "bulk_create"):
                body = {"items": [_sample_body(ep)]} if kind == "bulk_create" else _sample_body(ep)
                request["header"].append({"key": "Content-Type", "value": "application/json"})
                request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                                   "options": {"raw": {"language": "json"}}}
            requests.append({"name": f"{kind.replace('_', ' ')} {ep.name}", "request": request})
        folders.append({"name": ep.name, "item": requests})

    auth: dict[str, Any] | None = None
    if spec.app.auth == AuthMode.API_KEY:
        auth = {"type": "apikey", "apikey": [
            {"key": "key", "value": "X-API-Key", "type": "string"},
            {"key": "value", "value": "{{apiKey}}", "type": "string"},
            {"key": "in", "value": "header", "type": "string"},
        ]}
    elif spec.app.auth == AuthMode.JWT:
        auth = {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]}
    collection: dict[str, Any] = {
        "info": {
            "name": spec.app.title,
            "description": spec.app.description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "version": spec.app.version,
        },
        "variable": [
            {"key": "baseUrl", "value": api_base_url(name)},
            {"key": "apiKey", "value": "", "description": "Your API key (Studio → Keys & settings)"},
            {"key": "token", "value": "", "description": "Bearer token, for JWT APIs"},
        ],
        "item": folders,
    }
    if auth:
        collection["auth"] = auth
    return collection


# ---------------------------------------------------------------- Python client

_SDK_HEADER = '''"""Python client for the "{title}" API ({version}). Generated by contractapi:
download it again from Studio after the API changes.

    export CONTRACTAPI_BASE_URL={base}
    export {cred_env}=...
    from {module} import *
    rows = list_{example}(limit=50)           # one page
    df = {example}_dataframe(status="paid")   # every matching row, as a pandas DataFrame
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import httpx

BASE_URL = os.environ.get("CONTRACTAPI_BASE_URL", "{base}")
API_KEY = os.environ.get("CONTRACTAPI_API_KEY", "")
TOKEN = os.environ.get("CONTRACTAPI_TOKEN", "")
_client = httpx.Client(base_url=BASE_URL, timeout=float(os.environ.get("CONTRACTAPI_TIMEOUT", "30")))


class ApiError(Exception):
    """The API refused the call; .status and .problem (RFC 9457) say why."""

    def __init__(self, status: int, problem: dict[str, Any]) -> None:
        self.status = status
        self.problem = problem
        super().__init__(f"{{status}} {{problem.get('title', '')}}: {{problem.get('detail', '')}}")


def _call(method: str, path: str, *, headers: dict[str, str] | None = None, **kwargs: Any) -> Any:
    sent = {{"Accept": "application/json", **(headers or {{}})}}
    if API_KEY:
        sent["X-API-Key"] = API_KEY
    if TOKEN:
        sent["Authorization"] = f"Bearer {{TOKEN}}"
    response = _client.request(method, path, headers=sent, **kwargs)
    if response.status_code >= 400:
        try:
            problem = response.json()
        except ValueError:
            problem = {{"title": response.reason_phrase, "detail": response.text[:300]}}
        raise ApiError(response.status_code, problem)
    return response.json() if response.content else None


def _pages(path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
    params = dict(params)
    while True:
        page = _call("GET", path, params=params)
        yield from page["items"]
        if page.get("next_cursor"):
            params["cursor"] = page["next_cursor"]
        elif "offset" in page and page["offset"] + page["limit"] < (page.get("total") or 0):
            params["offset"] = page["offset"] + page["limit"]
        else:
            return
'''


def _sdk_functions(ep: EndpointSpec, path: str, read_only: bool) -> list[str]:
    n = ep.name
    out: list[str] = []
    for kind, _method, _suffix in _operations(ep, read_only):
        if kind == "list":
            out.append(f'''
def list_{n}(**params: Any) -> dict[str, Any]:
    """One page of {n}. Filters: {", ".join(ep.filters) or "none"}; e.g. limit=, cursor=, fields=."""
    return _call("GET", "{path}", params=params)


def iter_{n}(**params: Any) -> Iterator[dict[str, Any]]:
    """Every matching {n} row, page by page."""
    return _pages("{path}", params)


def {n}_dataframe(**params: Any) -> Any:
    """Every matching {n} row as a pandas DataFrame (pip install pandas)."""
    import pandas as pd

    return pd.DataFrame(list(iter_{n}(**params)))
''')
        elif kind == "get":
            out.append(f'''
def get_{n}(item_id: Any, **params: Any) -> dict[str, Any]:
    return _call("GET", f"{path}/{{item_id}}", params=params)
''')
        elif kind == "create":
            out.append(f'''
def create_{n}(data: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
    """Pass the same idempotency_key when retrying, so the row is never created twice."""
    headers = {{"Idempotency-Key": idempotency_key}} if idempotency_key else None
    return _call("POST", "{path}", json=data, headers=headers)
''')
        elif kind == "bulk_create":
            out.append(f'''
def bulk_create_{n}(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Up to 100 rows: {{"items": [created...], "errors": [{{"index", "status", "detail"}}]}}."""
    return _call("POST", "{path}/bulk", json={{"items": rows}})
''')
        elif kind in ("update", "replace"):
            verb = "PATCH" if kind == "update" else "PUT"
            out.append(f'''
def {kind}_{n}(item_id: Any, data: dict[str, Any], etag: str | None = None) -> dict[str, Any]:
    """Pass etag (from a read) to refuse the change if someone else changed the row first."""
    headers = {{"If-Match": etag}} if etag else None
    return _call("{verb}", f"{path}/{{item_id}}", json=data, headers=headers)
''')
        elif kind == "delete":
            out.append(f'''
def delete_{n}(item_id: Any, etag: str | None = None) -> None:
    headers = {{"If-Match": etag}} if etag else None
    _call("DELETE", f"{path}/{{item_id}}", headers=headers)
''')
        elif kind == "restore":
            out.append(f'''
def restore_{n}(item_id: Any) -> dict[str, Any]:
    return _call("POST", f"{path}/{{item_id}}/restore")
''')
    return out


def build_python_sdk(spec: ApiSpec, name: str | None = None) -> str:
    prefix = spec.app.api_prefix or ""
    base = api_base_url(name)
    cred_env = "CONTRACTAPI_TOKEN" if spec.app.auth == AuthMode.JWT else "CONTRACTAPI_API_KEY"
    example = spec.endpoints[0].name if spec.endpoints else "rows"
    parts = [_SDK_HEADER.format(title=spec.app.title, version=spec.app.version, base=base,
                                cred_env=cred_env, module=f"{name or 'api'}_sdk", example=example)]
    for ep in spec.endpoints:
        parts.extend(_sdk_functions(ep, f"{prefix}{ep.path}", spec.app.read_only))
    return "\n".join(parts).rstrip() + "\n"
