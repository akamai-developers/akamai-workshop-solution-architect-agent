# Module 2: Real data with MCP

**Goal:** stop the agent from guessing about your account and let it read real Akamai
Cloud (Linode) resources through a read-only MCP server.

**The problem you will see:** asked "what LKE clusters do I have?", the Module 1 agent
makes up plausible answers, because it has no access to your account.

**What you will learn:** the Model Context Protocol (MCP), how a server exposes tools
over a transport, calling it raw to see the protocol, then wiring it into a Strands
agent so the model reads live data.

## Planned sections (same template as Module 1: raw, then framework)
1. Setup (install `mcp`, point at the `akamai-cloud-mcp` server)
2. Configure (LINODE_TOKEN, server command, domains)
3. Talk to the MCP server raw: `initialize`, `list_tools`, `call_tool`, print the raw result
4. The agent without real data still guesses
5. Wire MCP into the agent by hand (list tools, pass schemas to the loop from Module 1)
6. The same with Strands `MCPClient` (lifecycle, `list_tools_sync`)
7. Scope the tools for a small model (`--domains`, `--max-results`) and the read-only safety story
8. Things to know (read-only by design, secret scrubbing, the `linode_` prefix, stdio vs streamable-http)

## Needs
- A read-only `LINODE_TOKEN`
- The `akamai-cloud-mcp` server (local checkout via `AKAMAI_MCP_DIR`, or published `uvx akamai-cloud-mcp`)

## Files
- `02_real_data_with_mcp.ipynb` — the lab
- `architecture.html` — diagram source, rendered to `../images/02_mcp_architecture.png`

_Status: scaffolded._
