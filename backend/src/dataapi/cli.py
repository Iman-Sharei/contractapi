"""CLI for dataapi — init, introspect, validate, diff, run."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import uvicorn
import yaml
from rich.console import Console
from rich.table import Table as RichTable

from dataapi import __version__
from dataapi.application.data_api_builder import create_data_app
from dataapi.application.openapi_diff import diff_openapi
from dataapi.application.studio_service import validate_spec_payload
from dataapi.domain.models.spec import dump_spec, load_spec, parse_spec
from dataapi.infrastructure.db.introspect import introspect_schema
from dataapi.infrastructure.persistence import spec_repo

app = typer.Typer(
    name="dataapi",
    help="Spec-first Postgres → FastAPI builder (opt-in endpoints, safe queries).",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command("version")
def version_cmd() -> None:
    """Show package version."""
    console.print(f"dataapi {__version__}")


@app.command("introspect")
def introspect_cmd(
    database_url: str = typer.Option(..., "--url", "-u", envvar="DATABASE_URL"),
    schema: str = typer.Option("public", "--schema", "-s"),
) -> None:
    """Show tables/views and flag sensitive columns."""
    tables = introspect_schema(database_url, schema=schema)
    if not tables:
        console.print(f"[yellow]No tables/views in schema '{schema}'.[/yellow]")
        raise typer.Exit(0)

    for t in tables:
        rich = RichTable(title=f"{t.schema}.{t.name}" + (f" ({t.kind})" if t.kind != "table" else ""))
        rich.add_column("Column")
        rich.add_column("Type")
        rich.add_column("Nullable")
        rich.add_column("PK")
        rich.add_column("Sensitive")
        rich.add_column("Comment")
        for c in t.columns:
            rich.add_row(
                c.name,
                c.type,
                "yes" if c.nullable else "no",
                "yes" if c.primary_key else "",
                "[red]YES[/red]" if c.sensitive else "",
                (c.comment or "")[:40],
            )
        console.print(rich)


@app.command("validate")
def validate_cmd(
    config: Path = typer.Argument(..., exists=True, dir_okay=False),
    check_db: bool = typer.Option(True, "--check-db/--no-check-db"),
) -> None:
    """Validate API specification."""
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    result = validate_spec_payload(raw, check_db=check_db)
    if result["warnings"]:
        for w in result["warnings"]:
            console.print(f"[yellow]warn[/yellow] {w}")
    if not result["valid"]:
        for e in result["errors"]:
            console.print(f"[red]error[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]OK[/green] {result['endpoint_count']} endpoint(s)")


@app.command("diff")
def diff_cmd(
    before: Path = typer.Argument(..., exists=True, dir_okay=False),
    after: Path = typer.Argument(..., exists=True, dir_okay=False),
    fail_on_breaking: bool = typer.Option(
        False,
        "--fail-on-breaking",
        help="Exit 1 if breaking OpenAPI changes are detected.",
    ),
) -> None:
    """Diff OpenAPI surfaces of two YAML specs."""
    before_spec = load_spec(before)
    after_spec = load_spec(after)
    before_doc = spec_repo.export_openapi_dict(before_spec)
    after_doc = spec_repo.export_openapi_dict(after_spec)
    result = diff_openapi(before_doc, after_doc)
    summary = result["summary"]
    console.print(
        f"added={summary['added']} updated={summary['updated']} "
        f"removed={summary['removed']} breaking={result['breaking']}"
    )
    for change in result.get("changes") or []:
        mark = {"NEW": "+", "DELETE": "−", "UPDATE": "~"}.get(change.get("type"), "?")
        br = " [red]BREAKING[/red]" if change.get("breaking") else ""
        console.print(f"  {mark} {change.get('method')} {change.get('path')}{br}")
    if fail_on_breaking and result["breaking"]:
        raise typer.Exit(1)


@app.command("serve")
@app.command("run")
def run_cmd(
    config: Optional[Path] = typer.Argument(None),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    studio: bool = typer.Option(
        True,
        "--studio/--data-only",
        help="Run full studio plane (default) or only the data API from a YAML file.",
    ),
) -> None:
    """Serve studio (+ /data) or a standalone data API from YAML."""
    if config is not None and not config.exists():
        console.print(f"[red]Config not found:[/red] {config}")
        raise typer.Exit(1)

    if studio and config is None:
        console.print(f"Studio on http://{host}:{port}  (docs: /docs, data: /data/docs)")
        uvicorn.run("dataapi.main:app", host=host, port=port, reload=False)
        return

    if config is None:
        console.print("[red]Config YAML required for --data-only[/red]")
        raise typer.Exit(1)

    spec = load_spec(config)
    # Preflight validate against DB when possible
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    result = validate_spec_payload(raw, check_db=True)
    if not result["valid"]:
        for e in result["errors"]:
            console.print(f"[red]error[/red] {e}")
        raise typer.Exit(1)

    fastapi_app = create_data_app(spec)
    console.print(f"Data API [bold]{spec.app.title}[/bold] on http://{host}:{port}/docs")
    uvicorn.run(fastapi_app, host=host, port=port, reload=False)


@app.command("init")
def init_cmd(
    output: Path = typer.Argument(Path("dataapi.yaml")),
    template: str = typer.Option(
        "readonly",
        "--template",
        "-t",
        help="readonly | jwt | sql | webhooks",
    ),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Write a starter YAML specification from a template."""
    if output.exists() and not force:
        console.print(f"[red]{output} already exists[/red] (use --force)")
        raise typer.Exit(1)
    examples = Path(__file__).resolve().parents[2] / "examples"
    mapping = {
        "readonly": "dataapi.yaml",
        "jwt": "jwt_write.yaml",
        "sql": "sql_metrics.yaml",
        "webhooks": "webhooks.yaml",
    }
    filename = mapping.get(template)
    if not filename:
        console.print(f"[red]Unknown template[/red]: {template} (readonly|jwt|sql|webhooks)")
        raise typer.Exit(1)
    sample = examples / filename
    if sample.exists():
        output.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        output.write_text(dump_spec(parse_spec(yaml.safe_load(_FALLBACK))), encoding="utf-8")
    console.print(f"Wrote [green]{output}[/green] (template={template})")


@app.command("doctor")
def doctor_cmd(
    database_url: Optional[str] = typer.Option(None, "--url", "-u", envvar="DATABASE_URL"),
) -> None:
    """Quick health checks for local development."""
    from dataapi.core.config import get_settings

    settings = get_settings()
    console.print(f"dataapi {__version__}")
    console.print(f"environment={settings.environment}")
    console.print(f"specs_dir={settings.specs_dir}")
    console.print(f"studio_api_key_set={'yes' if settings.studio_api_key else 'no'}")
    console.print(f"data_api_keys={len(settings.data_api_key_set)}")
    console.print(f"redis={'yes' if settings.redis_url else 'no'}")
    if database_url:
        try:
            tables = introspect_schema(database_url)
            console.print(f"[green]database ok[/green] tables/views={len(tables)}")
        except Exception as exc:
            console.print(f"[red]database error[/red] {exc}")
            raise typer.Exit(1) from exc


_FALLBACK = """\
database:
  url: postgresql://postgres:postgres@localhost:5433/app
app:
  title: My Data API
  version: 0.1.0
  read_only: true
  auth: api_key
  api_prefix: /v1
  rate_limit:
    enabled: true
    requests_per_minute: 120
endpoints:
  - name: customers
    path: /customers
    table: customers
    schema: public
    methods: [GET]
    primary_key: id
    fields: [id, name, email, created_at]
    filters: [email, name]
    sortable: [id, created_at, name]
    pagination:
      enabled: true
      mode: cursor
      default_limit: 20
      max_limit: 100
"""


@app.command("worker")
def worker_cmd(
    once: bool = typer.Option(False, "--once", help="Process a single job then exit"),
) -> None:
    """Drain the Redis job queue (horizontal async writes). Requires REDIS_URL + JOB_QUEUE_ENABLED."""
    from dataapi.application.jobs import process_next_job
    from dataapi.core.config import get_settings

    settings = get_settings()
    if not settings.redis_url:
        console.print("[red]REDIS_URL is required for worker mode[/red]")
        raise typer.Exit(1)
    if not settings.job_queue_enabled:
        console.print("[yellow]JOB_QUEUE_ENABLED is false — enabling for this process[/yellow]")
    console.print(f"[cyan]Listening on[/cyan] {settings.job_queue_key}")
    if once:
        job_id = process_next_job(timeout_seconds=10)
        if job_id:
            console.print(f"[green]processed[/green] {job_id}")
        else:
            console.print("[yellow]no job[/yellow]")
        return
    while True:
        job_id = process_next_job(timeout_seconds=5)
        if job_id:
            console.print(f"[green]processed[/green] {job_id}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
