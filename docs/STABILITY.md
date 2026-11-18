# Stability & SemVer (Beta)

**Status:** `0.6.0` — **Beta**. Suitable for early production on a **single self-hosted node** with known limits.

## What is stable in 0.6.x

| Surface | Stability |
|---------|-----------|
| YAML `ApiSpec` fields documented in examples | **Stable** — additive preferred; removals only in minor with deprecation |
| Data-plane HTTP under `/data` + `/apis/{name}` for table/SQL endpoints | **Stable** for listed features |
| CLI: `init`, `validate`, `serve`, `diff`, `doctor`, `version`, `worker` | **Stable** command names |
| Studio control-plane `/studio/*` | **Stable enough** for Studio UI; breaking changes announced in CHANGELOG |

## GA (optional config / extras; no experimental gate)

- Parquet list export (`pyarrow`)
- DuckDB driver
- GraphQL facade (`strawberry`) — table + SQL reads, nested relations, token-based RBAC + row-level, mutations, poll subscriptions
- Aggregation DSL (`aggregate:`) — metrics + where/having/windows
- Snowflake / BigQuery drivers (optional extras)
- Studio OIDC JWKS + browser cookie BFF (`STUDIO_OIDC_*`) — API key remains break-glass
- dbt import + git branch browser in Studio
- Redis horizontal job queue + `contractapi worker`
- Multi-active `/apis/{name}` alongside primary `/data`

## Versioning rules

1. **0.6.x Beta** — bugfixes + additive features; rare breaking YAML changes only with `UPGRADING.md` note.
2. **1.0.0** — after ≥1 real external deploy cycle.
3. Pre-releases use PEP 440: `0.7.0b1`, `0.7.0rc1`.
4. YAML default `app.api_prefix` is `/v1`; the Studio wizard writes `""` explicitly.

## Deprecation policy

- Deprecated fields stay ≥ **one minor** (e.g. 0.5 → 0.6) before removal.
- Studio UI may lag YAML by one release; server `dump-yaml` is source of truth.

## Support matrix

See [COMPATIBILITY.md](COMPATIBILITY.md).
