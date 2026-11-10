# Stability & SemVer (Beta)

**Status:** `0.5.0` — **Beta**. Suitable for early production on a **single self-hosted node** with known limits.

## What is stable in 0.5.x

| Surface | Stability |
|---------|-----------|
| YAML `ApiSpec` fields documented in examples | **Stable** — additive preferred; removals only in minor with deprecation |
| Data-plane HTTP under `/data` + `/apis/{name}` for table/SQL endpoints | **Stable** for listed features |
| CLI: `init`, `validate`, `serve`, `diff`, `doctor`, `version`, `worker` | **Stable** command names |
| Studio control-plane `/studio/*` | **Stable enough** for Studio UI; breaking changes announced in CHANGELOG |

## GA (optional config / extras; no experimental gate)

- Parquet list export (`pyarrow`)
- DuckDB driver
- GraphQL facade (`strawberry`) — table + SQL reads; table create/update/delete mutations
- Studio OIDC JWKS (`STUDIO_OIDC_ISSUER`) — API key remains break-glass
- Redis horizontal job queue + `contractapi worker`
- Multi-active `/apis/{name}` alongside primary `/data`

## Versioning rules

1. **0.5.x Beta** — bugfixes + additive features; rare breaking YAML changes only with `UPGRADING.md` note.
2. **1.0.0** — after ≥1 real external deploy cycle.
3. Pre-releases use PEP 440: `0.5.0b1`, `0.5.0rc1`.

## Deprecation policy

- Deprecated fields stay ≥ **one minor** (e.g. 0.5 → 0.6) before removal.
- Studio UI may lag YAML by one release; server `dump-yaml` is source of truth.

## Support matrix

See [COMPATIBILITY.md](COMPATIBILITY.md).
