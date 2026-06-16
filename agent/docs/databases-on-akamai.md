# Databases on Akamai for the agent

This is a design doc for adding Akamai Managed PostgreSQL to the Akamai Cloud Solutions Architect agent. It follows the patterns the agent already uses. Nothing here is a rewrite. Each piece is opt-in, the same way sessions are.

## How the agent works today

Two facts ground this design.

The documentation specialist tool `docs_lookup` (in `src/orchestrator.py`) does keyword search over a local `llms.txt` index at `DOCS_INDEX_PATH`. It tokenizes the question, drops stop words, scores each index entry by whole-word overlap (title weighted higher than description and URL), takes the top 3, and fetches those doc pages live from `techdocs.akamai.com`. It returns the page text with source URLs. There are no embeddings. A question about "object store buckets" will not match a page titled "S3-compatible storage" unless the words literally overlap.

Sessions are a pluggable backend (`src/sessions.py`). `make_session_manager` reads `SESSION_BACKEND` and returns `memory` (no manager, in-process), `file` (a local or mounted volume), or `s3` (`AkamaiObjectStorageSessionManager` in `src/akamai_sessions.py`, backed by Akamai Object Storage). The caller picks the backend with an env var. The agent code does not change when you switch.

That second fact is the template for everything below. A database backend is another entry in a selector.

## 1. RAG over the Akamai docs with Managed PostgreSQL and pgvector

`docs_lookup` works, but keyword overlap is a weak retriever. It misses synonyms, paraphrases, and questions that use different words than the docs. Vector similarity fixes that. You embed the question and the doc chunks into the same space and retrieve by distance, not by shared tokens.

### What changes

The retrieval step inside `docs_lookup` becomes pluggable, exactly like `make_session_manager`. Add a `DOCS_RETRIEVAL` env var with two values:

- `keyword` (default): the current `_docs_search`. Nothing changes. No new dependency, no database, no embeddings.
- `pgvector` (opt-in): embed the question, run a similarity query against Managed PostgreSQL, return the matching chunks.

`docs_lookup` keeps its signature and its job. It still returns page text with source URLs to the documentation specialist. The specialist prompt does not change. Only the function that produces the candidate set changes.

```python
def _docs_search(question, k=3):
    if settings.docs_retrieval == "pgvector":
        return _pgvector_search(question, k)
    return _keyword_search(question, k)  # today's code
```

This is the same shape as the session selector. One env var, one branch, a default that needs no infrastructure.

### Why pgvector here

Today `docs_lookup` fetches pages live on every call. With pgvector you embed the doc text once and store the chunk text alongside the vector and the source URL. At query time you embed only the question and run one indexed similarity query. You retrieve text you already have, so you can drop the live fetch on the hot path. The source URL travels with the row, so citations still work.

One database does both the vector search and the relational work in the rest of this doc. That is the reason to put it on Managed PostgreSQL instead of a separate vector service. Fewer moving parts to run.

### Minimal schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE docs_chunks (
    id          BIGSERIAL PRIMARY KEY,
    source_url  TEXT NOT NULL,
    title       TEXT,
    chunk       TEXT NOT NULL,
    embedding   VECTOR(1024) NOT NULL,   -- match your embedding model's dim
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cosine distance index. Build it after the table is populated.
CREATE INDEX docs_chunks_embedding_idx
    ON docs_chunks USING hnsw (embedding vector_cosine_ops);
```

The query the `pgvector` branch runs:

```sql
SELECT source_url, title, chunk
FROM docs_chunks
ORDER BY embedding <=> $1   -- $1 is the question embedding
LIMIT $2;                   -- k
```

`<=>` is cosine distance. Lower is closer.

### Scope

This doc does not specify the ingestion pipeline. Populating `docs_chunks` (walk the `llms.txt` index, fetch pages, chunk them, embed, upsert) is a separate batch job, the same role `refresh_docs_index.py` plays for the keyword index today. Treat it as out of scope here. The point of this section is the retrieval backend and the schema, not the loader.

## 2. Long-term memory

Sessions hold one conversation. When the conversation ends, or when a different `session_id` connects, that history is not in scope. That is correct for a transcript. It is wrong for durable facts.

Long-term memory is a separate store of facts and preferences that should outlive any single session. Examples: a user's default region is `us-sea-1`, their account runs LKE not bare compute, they always want monthly cost as well as hourly. These are not turns in a conversation. They are things the agent should know on the next conversation, under a different session id.

Store them in the same database, retrieved by similarity so the agent can pull the few facts relevant to the current question instead of loading everything.

```sql
CREATE TABLE memory (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    fact       TEXT NOT NULL,
    embedding  VECTOR(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX memory_user_idx ON memory (user_id);
CREATE INDEX memory_embedding_idx
    ON memory USING hnsw (embedding vector_cosine_ops);
```

Retrieval is the same vector query as docs, scoped to the user:

```sql
SELECT fact
FROM memory
WHERE user_id = $1
ORDER BY embedding <=> $2
LIMIT $3;
```

Keep this distinct from sessions in the code too. Sessions stay where they are, behind `SESSION_BACKEND`. Long-term memory is its own optional lookup, off unless configured. The two never share a code path. Sessions are the transcript of the current conversation. Long-term memory is what the agent carries between conversations.

## 3. Operational and eval state

Not everything needs vectors. Some of what the agent produces is plain relational data, and it belongs in normal tables in the same Managed PostgreSQL instance.

- **Run logs.** The logging hook already records what ran. Writing those records to a table gives you queryable history: which tool ran, for which session, how long it took, what it returned.
- **Approvals.** The approval gate (`src/hooks/approval_hook.py`) issues a one-time token for each planned write and runs the write only when a matching out-of-band grant arrives. An `approvals` table is the audit trail: planned change, token, who approved, when, whether the write ran. That is a durable record of every mutation the agent was allowed to make.
- **Eval results.** The eval harness (`evals/harness.py`) runs real prompts against the live model and produces a scorecard rather than pass/fail. Those scorecards are time series. Store each run's checks and outcomes in a table and you can track whether the agent is getting better or worse across model changes.

These are ordinary tables with foreign keys and timestamps. No extension, no embeddings. Sketch:

```sql
CREATE TABLE run_logs (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT,
    tool        TEXT NOT NULL,
    duration_ms INTEGER,
    ok          BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE approvals (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT,
    tool        TEXT NOT NULL,
    planned     TEXT NOT NULL,
    token       TEXT NOT NULL,
    granted     BOOLEAN NOT NULL DEFAULT FALSE,
    executed    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE eval_runs (
    id         BIGSERIAL PRIMARY KEY,
    case_name  TEXT NOT NULL,
    passed     BOOLEAN NOT NULL,
    detail     JSONB,
    model      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

These are also opt-in. The hooks and the harness keep working with no database. A configured connection adds a write to a table. It does not change what they do.

## Summary

Three backends, one Managed PostgreSQL instance. Docs RAG and long-term memory use pgvector. Operational and eval state use plain tables. Every piece is selected by an env var with a default that needs no database, the same pattern as `SESSION_BACKEND`. Adding Postgres is additive. Removing it leaves the agent running on its current defaults.

## Other uses

- **Feature flags.** A small table the agent reads at startup to toggle tools or demo mode per deployment.
- **Cache.** Memoize expensive read-tool results (region availability, catalog prices) with a TTL column instead of refetching.
- **Analytics.** Query `run_logs` and `eval_runs` for usage and quality trends over time.
