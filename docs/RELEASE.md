# Release checklist

## Maintainer (local)

```bash
# 1) tests
make test

# 2) build wheel
cd backend && python -m build

# 3) dry-run publish (needs PyPI token — YOU must log in)
twine check dist/*
# twine upload dist/*   # requires PyPI account + API token
```

## You must authenticate for

| Action | Where |
|--------|--------|
| `twine upload` / `uv publish` | [pypi.org](https://pypi.org) account + API token |
| `git push` / create GitHub repo | GitHub login |
| Push images to GHCR/Docker Hub | registry login |
| Real OIDC e2e against company IdP | IdP admin |

Script helper: `scripts/release_pypi.sh` (builds + checks; upload is interactive).
