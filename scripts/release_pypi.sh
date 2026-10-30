#!/usr/bin/env bash
# Build + check the contractapi distribution.
# Publishing requires YOUR PyPI login / token — this script will not upload unless you pass --upload.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

python -m pip install -U build twine >/dev/null
rm -rf dist build
python -m build
twine check dist/*

echo ""
echo "Artifacts in backend/dist/"
ls -la dist/

if [[ "${1:-}" == "--upload" ]]; then
  echo "Uploading to PyPI (needs TWINE_USERNAME=__token__ and TWINE_PASSWORD=pypi-... )"
  twine upload dist/*
else
  echo ""
  echo "Dry-run complete. To publish (requires PyPI API token):"
  echo "  export TWINE_USERNAME=__token__"
  echo "  export TWINE_PASSWORD=pypi-AgEIcHlwaS5vcmc..."
  echo "  ./scripts/release_pypi.sh --upload"
fi
