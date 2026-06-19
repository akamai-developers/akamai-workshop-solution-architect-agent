# Akamai Cloud Solutions Architect agent.
# Serves the orchestrator over HTTP on port 8080. Build from the agent/ directory:
#   docker build -f deploy/Dockerfile -t ghcr.io/<you>/akamai-sa-agent:latest .

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Graphviz system binary (`dot`): the `diagrams` package shells out to it to
# render architecture diagrams. The pip packages alone are not enough.
RUN apt-get update \
    && apt-get install -y --no-install-recommends graphviz \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY scripts ./scripts
# The documentation specialist's docs index (llms.txt).
COPY data ./data

ENV FASTEMBED_CACHE=/app/data/fastembed \
    DOCS_INDEX_PATH=/app/data/llms.txt \
    DOCS_INDEX_DIR=/app/data/docs_index

# Bake the ONNX model AND the semantic page index (embed the llms.txt entries;
# no crawl - Akamai's WAF blocks that, and page bodies are fetched live per query
# at runtime). Embedding the corpus HERE means the runtime only loads a ~1MB
# matrix and embeds the single query, so the pod never spikes memory. Own layer
# => cached unless scripts/ or data/ change.
RUN pip install --upgrade pip \
    && pip install fastembed numpy \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/data/fastembed')" \
    && python scripts/build_docs_index.py

COPY src ./src

# sessions: boto3 for Object Storage. telemetry: Langfuse. akamai-cloud-mcp: the
# read-only account tool server, baked in so it runs over stdio in-cluster.
RUN pip install ".[telemetry,sessions]" akamai-cloud-mcp

ENV MCP_COMMAND=akamai-cloud-mcp \
    MCP_ARGS="--domains regions,pricing,compute,lke,object_storage,networking,account --max-results 25"

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8080"]
