"""Build a Postman Collection v2.1 from an ApiSpec."""

from __future__ import annotations

from typing import Any

from contractapi.domain.models.spec import ApiSpec, HttpMethod


def build_postman_collection(spec: ApiSpec, *, base_url: str = "{{baseUrl}}") -> dict[str, Any]:
    prefix = spec.app.api_prefix or ""
    items = []
    for ep in spec.endpoints:
        reqs = []
        for method in ep.methods:
            url_path = f"{prefix}{ep.path}"
            query = []
            if method == HttpMethod.GET:
                query = [
                    {"key": "limit", "value": str(ep.pagination.default_limit)},
                    {"key": "fields", "value": ",".join(ep.fields[:5]), "disabled": True},
                ]
                if ep.search_param:
                    query.append({"key": ep.search_param, "value": "", "disabled": True})
            body = None
            if method in {HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH}:
                sample = {f: f"<{f}>" for f in (ep.writable_fields or ep.fields[:3])}
                body = {
                    "mode": "raw",
                    "raw": __import__("json").dumps(sample, indent=2),
                    "options": {"raw": {"language": "json"}},
                }
            headers = [{"key": "Accept", "value": "application/json"}]
            if spec.app.auth.value == "api_key":
                headers.append({"key": "X-API-Key", "value": "{{apiKey}}"})
            if spec.app.auth.value == "jwt":
                headers.append({"key": "Authorization", "value": "Bearer {{token}}"})
            reqs.append(
                {
                    "name": f"{method.value} {ep.name}",
                    "request": {
                        "method": method.value,
                        "header": headers,
                        "body": body,
                        "url": {
                            "raw": f"{base_url}/data{url_path}",
                            "host": [base_url.replace("://", "://").split("://")[-1] or "localhost"],
                            "path": ["data", *[p for p in url_path.strip("/").split("/") if p]],
                            "query": query,
                        },
                        "description": ep.description or "",
                    },
                }
            )
        items.append({"name": ep.name, "item": reqs})

    return {
        "info": {
            "name": spec.app.title,
            "description": spec.app.description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "version": spec.app.version,
        },
        "variable": [
            {"key": "baseUrl", "value": "http://127.0.0.1:8000"},
            {"key": "apiKey", "value": ""},
            {"key": "token", "value": ""},
        ],
        "item": items,
    }
