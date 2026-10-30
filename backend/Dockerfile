FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY examples ./examples
RUN pip install --no-cache-dir ".[redis]"

ENV SPECS_DIR=/data/specs \
    AUDIT_LOG_PATH=/data/logs/audit.jsonl \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data/specs /data/logs
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "dataapi.main:app", "--host", "0.0.0.0", "--port", "8000"]
