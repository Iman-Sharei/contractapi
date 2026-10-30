from pathlib import Path

from typer.testing import CliRunner

from contractapi.cli import app

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "contractapi" in result.stdout


def test_cli_validate_examples_no_db():
    for name in ("contractapi.yaml", "jwt_write.yaml", "sql_metrics.yaml", "webhooks.yaml"):
        path = EXAMPLES / name
        result = runner.invoke(app, ["validate", str(path), "--no-check-db"])
        assert result.exit_code == 0, result.stdout + result.stderr


def test_cli_diff_non_breaking_self():
    path = EXAMPLES / "contractapi.yaml"
    # Same file may still need DB for openapi export — skip if fails
    result = runner.invoke(app, ["diff", str(path), str(path)])
    if result.exit_code != 0 and "connect" in (result.stdout + result.stderr).lower():
        return
    assert result.exit_code == 0
    assert "breaking=False" in result.stdout or "breaking=false" in result.stdout.lower()
