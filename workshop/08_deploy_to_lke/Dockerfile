# Akamai Cloud Solutions Architect, packaged for Akamai LKE.
#
# Serves the Module 7 orchestrator over HTTP (the FastAPI app in src/api.py) on port 8080,
# ready for a plain Kubernetes Deployment behind a NodeBalancer.
#
# Build from the repo root:
#   docker build -f workshop/08_deploy_to_lke/Dockerfile -t ghcr.io/<you>/akamai-sa-agent:latest .

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

# The documentation specialist's local docs index, baked in. The agent searches it,
# then fetches the matching pages live from techdocs.akamai.com.
COPY workshop/07_multi_agent/data/llms.txt /app/data/llms.txt

# sessions:   boto3, for durable sessions on Akamai Object Storage
# telemetry:  Langfuse tracing when its env is set
# akamai-cloud-mcp: the read tool server, baked in so the agent runs it over stdio
RUN pip install --upgrade pip && pip install ".[telemetry,sessions]" akamai-cloud-mcp

# Serve the orchestrator, and run the baked-in MCP server as its console script.
ENV AGENT_MODE=orchestrator \
    DOCS_INDEX_PATH=/app/data/llms.txt \
    MCP_COMMAND=akamai-cloud-mcp \
    MCP_ARGS="--domains regions,pricing,compute,lke,object_storage,networking,account --max-results 25"

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8080"]
