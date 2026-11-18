"""List export formats: CSV, NDJSON, Parquet."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi.responses import PlainTextResponse, Response

from contractapi.core.errors import AppError


def _csv_response(items: list[dict[str, Any]], fields: list[str]) -> PlainTextResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in items:
        writer.writerow({k: row.get(k) for k in fields})
    return PlainTextResponse(buf.getvalue(), media_type="text/csv; charset=utf-8")


def _ndjson_response(items: list[dict[str, Any]], fields: list[str]) -> PlainTextResponse:
    lines = [json.dumps({k: row.get(k) for k in fields}, default=str) for row in items]
    return PlainTextResponse("\n".join(lines) + ("\n" if lines else ""), media_type="application/x-ndjson")


def _parquet_response(items: list[dict[str, Any]], fields: list[str]) -> Response:
    """Serialize rows as Apache Parquet (requires optional pyarrow)."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/dependency-missing",
            title="Parquet support not installed",
            status=501,
            detail="Install with: pip install 'contractapi[parquet]'",
        ) from exc

    columns = {f: [row.get(f) for row in items] for f in fields}
    # Normalize non-Arrow-native values to strings
    for key, values in columns.items():
        columns[key] = [v if v is None or isinstance(v, (bool, int, float, str, bytes)) else str(v) for v in values]
    table = pa.table(columns)
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="zstd")
    return Response(
        content=sink.getvalue(),
        media_type="application/vnd.apache.parquet",
        headers={"Content-Disposition": 'attachment; filename="export.parquet"'},
    )
