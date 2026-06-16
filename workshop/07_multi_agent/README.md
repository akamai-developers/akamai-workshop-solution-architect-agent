# Module 7: Multi-agent, an orchestrator and specialists

**Goal:** split the one do-everything agent into a small team: focused specialist
agents, and an orchestrator that routes the work and calls each one like a tool.

**The problem you will see:** one agent carrying every tool and a prompt full of rules
for every job. A small model has to pick from a long tool list and follow all of it in
one pass, and it gets worse as you add more.

**What you will learn:** the "agents as tools" pattern in Strands. Wrap a specialist
agent in a `@tool` function so an orchestrator can call it. Build a documentation
specialist grounded in the real Akamai docs, an account specialist and a pricing
specialist split read-before-reason, and an orchestrator that routes a request and
combines the answers. And when not to wrap a tool in an agent.

## Sections (raw, then framework)
1. Setup
2. Configure the model (one shared model for every agent)
3. The problem: one agent wearing every hat
4. The fix: agents as tools
5. A specialist as a tool: documentation (local index, live fetch)
6. Two more specialists: account and pricing (read-before-reason)
7. The orchestrator (router prompt, one combined answer)
8. When not to wrap a tool in an agent
9. Where writes and the approval gate live

## Needs
- A read-only `LINODE_TOKEN` and the `akamai-cloud-mcp` server (as in Module 2)
- The local docs index: `python workshop/07_multi_agent/scripts/refresh_docs_index.py`
- The `graphviz` Python package and the `dot` binary for the diagram tool

## Files
- `07_multi_agent.ipynb` — the lab
- `scripts/refresh_docs_index.py` — download the Akamai docs index to `data/llms.txt`
- `data/llms.txt` — the local docs index (about 1.8 MB)
- `../images/07_multiagent_architecture.png` — the architecture diagram

_Status: complete._
