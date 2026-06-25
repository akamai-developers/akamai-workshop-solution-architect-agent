# Building AI Agents on Akamai Cloud

This repo helps developers and engineers build AI agents on Akamai Cloud. There are two ways to use it: build an agent step by step in the workshop, or run the agent that is already built.

Create an [Akamai Cloud account](http://login.linode.com/signup?promo=akm-dev-git-300-31126-M055) with an API token (includes free $300 credit)

The running example is an **Akamai Cloud Solutions Architect**: an agent that reads a real Linode account, prices resources, draws its own architecture, answers from the official docs, and makes changes only behind a human approval gate. Everything it needs runs on Akamai: the model on Akamai GPUs with vLLM, the agent on LKE, conversation memory in Object Storage, long-term memory in Managed PostgreSQL.

![The stack on Akamai](diagrams/stack_on_akamai.png)

## Two paths

### Build it: the workshop
Learn by building, one module at a time, from a first tool call to a deployed multi-agent. Eight modules: first agent and tools, real data with MCP, guardrails, memory and sessions, diagrams, evals, multi-agent, deploy to LKE.

Start at **[`workshop/README.md`](workshop/README.md)**, then open `workshop/01_first_agent`.

### Run it: the agent
The finished multi-agent orchestrator, ready to run locally, in Discord, or on LKE. It is the agent the workshop builds toward, complete.

Start at **[`agent/README.md`](agent/README.md)**.
- Chat locally: `cd agent && PYTHONPATH=src python -m orchestrator`
- In Discord: a bridge that connects outbound, so it needs no inbound exposure.
- On LKE: run it next to your vLLM endpoint, with memory in Object Storage and Managed PostgreSQL.

## Running in the Akamai workshop platform?
If your instructor used the Akamai workshop platform, you were handed an access card with a URL and a password. Open the URL, sign in, and you land in JupyterLab with this repo already cloned and the vLLM model endpoint already wired in. You do not configure the model. Open the `workshop/` folder and start at `01_first_agent`. The model runs on the Akamai GPU node the platform provisioned, and your notebook runs on a CPU node next to it.

## What is here
- **`workshop/`** the eight-module workshop. Start at its README.
- **`agent/`** the fully built agent, its Discord bridge, the deploy code, and design notes.
- **`diagrams/`** the architecture diagrams used across both.

## The goal
Help developers and engineers build AI agents on Akamai Cloud, and show that the whole agent and everything around it, the model, memory, account data, networking, and the edge, runs on Akamai.
