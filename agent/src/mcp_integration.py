"""Wire the akamai-cloud-mcp server as the agent's read-tool source.

Reads come from the akamai-cloud-mcp server (read-only, scrubbed) over stdio.
Writes stay local and gated. Until the server is published, it is run from a
local checkout with `uv run --directory <dir>`; once published, `uvx
akamai-cloud-mcp`.

Lifecycle matters: an MCPClient owns a stdio subprocess (the server) that lives
only while the client is started. Callers keep it open for as long as the agent
runs, then stop it. The CLI does this around its loop; the API does it in the
FastAPI lifespan.
"""

from __future__ import annotations

import os
import shlex

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands.tools.mcp import MCPClient

from config.settings import settings


def _command_and_args() -> tuple[str, list[str]]:
    """Resolve how to launch the read MCP server from settings."""
    if settings.mcp_args:
        # Full, explicit override.
        return settings.mcp_command, shlex.split(settings.mcp_args)

    scope = ["--domains", settings.mcp_domains, "--max-results", str(settings.mcp_max_results)]
    if settings.mcp_dir:
        # Local checkout, not yet published.
        directory = os.path.expanduser(settings.mcp_dir)
        return "uv", ["run", "--directory", directory, "akamai-cloud-mcp", *scope]
    # Published package.
    return "uvx", ["akamai-cloud-mcp", *scope]


def make_read_mcp_client() -> MCPClient:
    """Build (but do not start) an MCPClient for the akamai-cloud-mcp reads.

    The server reads one account via LINODE_TOKEN, passed through the
    environment. Regions and pricing work without a token; account-scoped tools
    need it.
    """
    env = dict(os.environ)
    if settings.linode_token:
        env["LINODE_TOKEN"] = settings.linode_token

    command, args = _command_and_args()
    params = StdioServerParameters(command=command, args=args, env=env)
    return MCPClient(lambda: stdio_client(params))
