# FastAPI endpoint style

Applies to the **control plane** (`interfaces/http/studio/*`) and to anything the **data-plane builder** (`application/data_api_builder.py`) generates.

## Control plane (Studio) routes

- Use `APIRouter` with `prefix`, `tags`, and router-level `dependencies=[Depends(require_studio_api_key)]` (see `studio/router.py`). Never mount a Studio route without that dependency.
- One request model and one response model per route, defined in `interfaces/http/studio/schemas.py` (Pydantic v2). Declare them: `response_model=...`, `status_code=...`. No bare `dict` bodies on new routes (the dbt import is a legacy exception).
- Each route: validate (Pydantic) → call an `application/` function → return. No business logic, no SQL, no `audit_event` inline decisions in the route body.
- Provide `summary=` and `responses={...}` for the expected error statuses (400/401/403/404/409/422/429) using the Problem Details model, so `/docs` shows them. No undocumented endpoints.
- Don't use class-based "ViewSet-like" CRUD generators for Studio routes; plain functions on a router.

## Data-plane (generated) endpoints

- Generated from `EndpointSpec`; **the spec decides what exists**. Never add a data-plane route that isn't driven by the spec.
- Path: `/{api_prefix}/{path}` with plural-noun resources, lowercase, hyphenated (`normalize_path` in `spec.py`). Resource names are nouns; HTTP method carries the verb.
- Methods: GET list/get, POST create, PATCH partial update, PUT replace (only if spec enables), DELETE. Safe/idempotent semantics respected; writes require explicit spec opt-in.
- Lists are always paginated with a hard max limit (`PaginationConfig`); cursor preferred over offset for large tables. Return `Link` headers where already patterned.
- Output models are derived from the **allowlisted fields only**; never serialize the raw row.
- OpenAPI must stay accurate: every generated route has summary, parameters, request/response schemas and the error responses it can produce. Check with `contractapi diff` (breaking-change detector) when changing generated shapes.

## Serializers / Pydantic

- Explicit field lists; never "all columns" for User-like tables.
- Optional field: `field: T | None = None`; don't add redundant defaults/validators for omit-vs-null unless null must clear a value (PATCH semantics).
- Validation errors surface as RFC 9457 `validation-error` (422) via the global handler; don't catch and reshape them.
