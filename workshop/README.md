# Getting started: build a Solution Architect agent on Akamai Cloud

A hands-on workshop. You will build an AI agent that runs on Akamai Cloud, reads a
real Linode account, makes changes safely behind a human approval gate, remembers
conversations, draws its own architecture, and is measured with evals. The running
example is an **Akamai Cloud Solutions Architect**: an assistant that helps
developers design and operate workloads on Akamai Cloud (Linode) compute,
Kubernetes, storage, networking, and GPUs.

Built with [Strands Agents](https://strandsagents.com) and a self-hosted model
served by [vLLM](https://docs.vllm.ai) on [Akamai Cloud GPUs](https://www.linode.com/products/gpu/).

## Who this is for

Developers who want to build real agents, not toys. Some Python helps. No prior
agent experience needed.

## What you will learn

Each module shows you a problem the agent actually has, then teaches the pattern
that fixes it.

| Module | You will see | You will learn |
|---|---|---|
| 1. First agent and tools | The model guess the date and the math | Built-in and custom tools, and the vLLM tool-calling flags |
| 2. Real data with MCP | The agent inventing account details | A read-only MCP server that gives it real data |
| 3. Guardrails | A change about to run unchecked | A deny-by-default approval gate for writes |
| 4. Memory and sessions | "What did I just ask?" | In-process memory, then durable sessions on Object Storage |
| 5. Diagrams that do not lie | A fabricated cluster diagram | Deterministic tools for small models |
| 6. Evals | "It felt fine" | Measure behavior, find a real gap, fix it, watch the number rise |
| 7. Multi-agent | One agent wearing every hat | An orchestrator that routes to focused specialist agents |
| 8. Deploy to LKE | It only runs on your laptop | Ship it to Kubernetes behind a NodeBalancer |

## Prerequisites

- Python 3.11+ and `git`
- A model endpoint: vLLM on Akamai Cloud, or any OpenAI-compatible endpoint
- For the account modules, a read-only [Linode API token](https://techdocs.akamai.com/cloud-computing/docs/manage-personal-access-tokens)

## Setup

1. Copy `.env.example` to `.env` and fill in your model endpoint and token.
2. Run the environment check and fix anything it flags:

   ```bash
   python workshop/scripts/verify_env.py
   ```

3. Open the notebooks in order. Run them locally with Jupyter, or open a notebook
   in Google Colab.

Each module is self-contained and builds toward the production agent, which is
already here, fully built, in [`../agent/`](../agent/). By the end you will
recognize every piece of it. If you would rather run the finished agent than
build it, start there.
