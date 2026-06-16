"""Self-report tool: which Akamai Cloud region this agent is running in.

Account-level region/inventory reads come from the akamai-cloud-mcp server. This
tool is different: it reports the agent's own deployment from the node metadata,
which the MCP server does not provide. Read-only, no approval required.
"""

from __future__ import annotations

from config.settings import settings
from strands import tool

from tools import _linode


@tool
def deployed_region() -> str:
    """Report the Akamai Cloud region this agent is running in.

    Reads the Linode Metadata Service from inside the node. Falls back to the
    AGENT_REGION env var when the metadata service is not reachable (for
    example when running off-cluster), so the agent never claims a region it
    cannot verify.

    Returns:
        The region slug and how it was determined.
    """
    region = _linode.metadata_region()
    if region:
        return f"Running in Akamai Cloud region '{region}' (from the Linode Metadata Service)."
    if settings.region_fallback:
        return (
            f"Metadata Service not reachable. Configured region is "
            f"'{settings.region_fallback}' (from AGENT_REGION env var)."
        )
    return (
        "Region is unknown: the Linode Metadata Service is not reachable and "
        "AGENT_REGION is not set. This usually means the agent is running "
        "off-cluster (for example on a laptop)."
    )
