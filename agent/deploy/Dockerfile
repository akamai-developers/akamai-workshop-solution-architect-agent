# Akamai Cloud Solutions Architect agent.
# Serves the orchestrator over HTTP on port 8080. Build from the agent/ directory:
#   docker build -f deploy/Dockerfile -t ghcr.io/<you>/akamai-sa-agent:latest .

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# The documentation specialist's local Akamai docs index.
COPY data ./data

# sessions: boto3 for Object Storage. telemetry: Langfuse. akamai-cloud-mcp: the
# read-only account tool server, baked in so it runs over stdio in-cluster.
RUN pip install --upgrade pip && pip install ".[telemetry,sessions]" akamai-cloud-mcp

ENV DOCS_INDEX_PATH=/app/data/llms.txt \
    MCP_COMMAND=akamai-cloud-mcp \
    MCP_ARGS="--domains regions,pricing,compute,lke,object_storage,networking,account --max-results 25"

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8080"]
