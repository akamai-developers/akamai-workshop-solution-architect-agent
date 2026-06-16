# The open-source agent stack on Akamai

The agent in this repo runs on Akamai. So can everything around it. The open-source agent tooling ecosystem is self-hostable, and it maps onto Akamai building blocks: LKE for compute, Managed PostgreSQL for relational and vector state, Object Storage for artifacts and backups, Block Storage for stateful pods, and a NodeBalancer with a Cloud Firewall in front.

This repo already self-hosts two of these. vLLM serves the model. Langfuse traces every run. The rest follow the same pattern.

## Why self-host the stack

- Your data stays in your account. Traces, memories, eval prompts, and guardrail decisions are the most sensitive data the agent touches. Self-hosting keeps them in your tenancy instead of a vendor's.
- You pay flat compute, not per-seat or per-trace SaaS pricing.
- Co-locating the tools with the agent on LKE keeps traffic on the internal network, so you cut latency and egress on high-volume calls.

## Observability and tracing

| Tool | What | Self-host | State on Akamai |
|---|---|---|---|
| Langfuse (MIT) | Traces, prompt management, evals, cost. This repo uses it. | Helm chart on LKE | Managed PostgreSQL (metadata), a ClickHouse pod and a Redis pod on LKE, Object Storage (event blobs) |
| Arize Phoenix (ELv2, free to self-host) | OpenTelemetry-native tracing UI | Helm or Docker on LKE | Managed PostgreSQL |
| Langtrace (AGPL-3.0) | OpenTelemetry observability dashboard | docker-compose on LKE | Managed PostgreSQL plus a ClickHouse pod |

## Agent memory

| Tool | What | Self-host | State on Akamai |
|---|---|---|---|
| mem0 (Apache-2.0) | Extracts and recalls facts from conversations | FastAPI server on LKE | Managed PostgreSQL with pgvector; optional Neo4j pod for graph memory |
| Letta (Apache-2.0) | Stateful agent memory, formerly MemGPT | Docker on LKE | Managed PostgreSQL with pgvector |
| Graphiti (Apache-2.0) | Temporal knowledge graph, the engine behind Zep | docker-compose on LKE | A Neo4j or FalkorDB pod on LKE |

## Vector store and RAG

| Tool | What | Self-host | State on Akamai |
|---|---|---|---|
| pgvector on Managed PostgreSQL | Vectors next to relational data, no new service | `CREATE EXTENSION vector` | Managed PostgreSQL |
| Qdrant (Apache-2.0) | Vector database with filtering and quantization | Helm StatefulSet on LKE | Block Storage volumes, backups to Object Storage |
| Weaviate (BSD-3) | Vector database with hybrid search | Helm StatefulSet on LKE | Block Storage volumes, backups to Object Storage |

## Model serving and gateway

| Tool | What | Self-host | State on Akamai |
|---|---|---|---|
| vLLM (Apache-2.0) | OpenAI-compatible serving. This repo uses it. | Helm on LKE GPU pools | Stateless; weights from Object Storage |
| LiteLLM (MIT) | One gateway over vLLM and many providers, with keys, budgets, rate limits | Helm on LKE | Managed PostgreSQL (keys and spend), a Redis pod |
| Ollama (MIT) | Single-binary serving with an OpenAI-compatible endpoint | Container on LKE | Stateless; models on Block Storage or Object Storage |

## Evaluation and testing

| Tool | What | Self-host | State on Akamai |
|---|---|---|---|
| Promptfoo (MIT) | Declarative evals and red-team runs | Docker or Helm on LKE | Block Storage volume (SQLite), Object Storage for reports. Single-node. |
| Ragas (Apache-2.0) | RAG and agent scoring library | Runs in your CI pods on LKE | Stateless; write scores to Managed PostgreSQL if you keep them |
| Langfuse evals (MIT) | Dataset and LLM-as-judge evals | The same Langfuse you run for tracing | As Langfuse above |

## Guardrails and safety

| Tool | What | Self-host | State on Akamai |
|---|---|---|---|
| NeMo Guardrails (Apache-2.0) | Input, output, and topic rails | REST service on LKE | Mostly stateless; pgvector for embedding rails |
| Guardrails AI (Apache-2.0) | Output validation server | Container on LKE | Stateless by default; Managed PostgreSQL for the management API |
| Llama Guard 3 on vLLM (Llama license) | A safety classifier model for prompts and responses | vLLM on an LKE GPU pool | Stateless |

## The Akamai mapping

- **Compute:** LKE, deployed with Helm. Stateless services as Deployments. Stateful ones (ClickHouse, Redis, Neo4j, Qdrant, Weaviate) as StatefulSets on Block Storage.
- **Relational and vector state:** Managed PostgreSQL with pgvector. The default home for tracing metadata, gateway keys, and memory vectors.
- **Artifacts and backups:** Object Storage, S3-compatible. Model weights, event blobs, vector snapshots, eval reports.
- **Access:** NodeBalancer for the front door, Cloud Firewall to scope it, VPC for private traffic between the agent and these services.
- **GPU:** the GPU node pool serves vLLM, and a safety model like Llama Guard when you want it.

## Honest notes

- Akamai manages PostgreSQL. It does not manage ClickHouse, Redis, or Neo4j, so those run as pods on LKE with persistent volumes. Still your cluster, your data, one bill.
- Licenses vary. Most here are MIT, Apache-2.0, or BSD. A few (Phoenix ELv2, Langtrace AGPL-3.0, Llama Guard) are source-available or copyleft but fully self-hostable. Check the license against your use.
