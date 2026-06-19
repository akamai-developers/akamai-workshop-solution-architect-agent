"""Runtime configuration, sourced from environment variables.

Everything the agent needs to know about its provider, credentials, and
demo-safety toggles lives here so the rest of the code reads one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    """Resolved configuration for one process."""

    # Model provider selection: openai | anthropic | vllm
    provider: str = field(default_factory=lambda: os.getenv("MODEL_PROVIDER", "openai").strip().lower())

    # Which agent the HTTP service serves: "flat" (one agent, all tools) or
    # "orchestrator" (the Module 7 multi-agent form). The LKE deploy sets orchestrator.
    agent_mode: str = field(default_factory=lambda: os.getenv("AGENT_MODE", "flat").strip().lower())

    # OpenAI
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model_id: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL_ID", "gpt-4.1-2025-04-14"))

    # Anthropic
    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    anthropic_model_id: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_MODEL_ID", "claude-sonnet-4-5-20250929")
    )

    # vLLM (OpenAI-compatible)
    vllm_base_url: str = field(default_factory=lambda: os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"))
    vllm_model_id: str = field(
        default_factory=lambda: os.getenv("VLLM_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct")
    )
    vllm_api_key: str = field(default_factory=lambda: os.getenv("VLLM_API_KEY", "placeholder"))

    # Akamai / Linode
    linode_token: str | None = field(default_factory=lambda: os.getenv("LINODE_TOKEN"))
    region_fallback: str | None = field(default_factory=lambda: os.getenv("AGENT_REGION") or None)

    # Safety
    demo_mode: bool = field(default_factory=lambda: _bool("DEMO_MODE", True))

    # Reads come from the akamai-cloud-mcp server (read-only). Writes stay local
    # and gated. When mcp is disabled or unreachable the agent falls back to the
    # local read tools, so offline tests and a hiccuping demo still work.
    mcp_enabled: bool = field(default_factory=lambda: _bool("MCP_ENABLED", True))
    mcp_command: str = field(default_factory=lambda: os.getenv("MCP_COMMAND", "uv"))
    # Full override of the argv after the command, space-separated. When unset
    # the args are derived from mcp_dir/mcp_domains/mcp_max_results below.
    mcp_args: str | None = field(default_factory=lambda: os.getenv("MCP_ARGS") or None)
    # Local checkout of the (not-yet-published) MCP server; run with `uv run`.
    # When unset, the published package is run with `uvx akamai-cloud-mcp`.
    mcp_dir: str | None = field(default_factory=lambda: os.getenv("AKAMAI_MCP_DIR") or None)
    mcp_domains: str = field(
        default_factory=lambda: os.getenv(
            "MCP_DOMAINS", "regions,pricing,compute,lke,object_storage,networking,account"
        )
    )
    mcp_max_results: int = field(default_factory=lambda: int(os.getenv("MCP_MAX_RESULTS", "25")))

    # Documentation specialist: a local copy of the Akamai docs index (llms.txt). The
    # docs specialist searches it, then fetches the matching pages live. Unset disables it.
    docs_index_path: str | None = field(default_factory=lambda: os.getenv("DOCS_INDEX_PATH") or None)

    # Sessions: memory (in-process only), file (volume), s3 (Akamai Object Storage).
    session_backend: str = field(
        default_factory=lambda: os.getenv("SESSION_BACKEND", "memory").strip().lower()
    )
    session_dir: str = field(default_factory=lambda: os.getenv("SESSION_DIR", "./.sessions"))
    session_bucket: str | None = field(default_factory=lambda: os.getenv("SESSION_BUCKET") or None)
    session_prefix: str = field(default_factory=lambda: os.getenv("SESSION_PREFIX", "sessions"))
    # Akamai Object Storage cluster, e.g. us-sea-1. Gives both the S3 endpoint
    # (https://<cluster>.linodeobjects.com) and the region the client reports.
    session_cluster: str | None = field(default_factory=lambda: os.getenv("SESSION_CLUSTER") or None)
    # Object Storage access keys, passed explicitly (no AWS_* variables). The
    # provisioning script issues a key limited to the sessions bucket.
    session_access_key: str | None = field(default_factory=lambda: os.getenv("SESSION_ACCESS_KEY") or None)
    session_secret_key: str | None = field(default_factory=lambda: os.getenv("SESSION_SECRET_KEY") or None)
    # Optional endpoint override, for clusters whose host is not
    # <cluster>.linodeobjects.com. Normally unset and derived from the cluster.
    session_endpoint_url: str | None = field(
        default_factory=lambda: os.getenv("SESSION_ENDPOINT_URL") or None
    )

    # Discord
    discord_token: str | None = field(default_factory=lambda: os.getenv("DISCORD_TOKEN") or None)
    # Optional. The server (guild) id to register slash commands to instantly. Without
    # it, commands sync globally and can take up to an hour to appear.
    discord_guild_id: str | None = field(default_factory=lambda: os.getenv("DISCORD_GUILD_ID") or None)

    # Heartbeat: the proactive, observe-and-report loop (heartbeat.py). Off unless
    # enabled. Needs the two channel ids to post; without them it runs but stays quiet.
    heartbeat_enabled: bool = field(default_factory=lambda: _bool("HEARTBEAT_ENABLED", False))
    heartbeat_tz: str = field(default_factory=lambda: os.getenv("HEARTBEAT_TZ", "America/New_York"))
    proactive_channel_id: str | None = field(default_factory=lambda: os.getenv("PROACTIVE_CHANNEL_ID") or None)
    ops_alerts_channel_id: str | None = field(default_factory=lambda: os.getenv("OPS_ALERTS_CHANNEL_ID") or None)
    # Firewall labels to ignore in the 0.0.0.0/0 drift check (intentionally public, e.g. vLLM).
    heartbeat_public_fw_allow: str = field(default_factory=lambda: os.getenv("HEARTBEAT_PUBLIC_FW_ALLOW", ""))

    # Langfuse
    langfuse_public_key: str | None = field(default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY") or None)
    langfuse_secret_key: str | None = field(default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY") or None)
    langfuse_host: str = field(default_factory=lambda: os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"))

    # Long-term memory: a Postgres connection string (Akamai Managed PostgreSQL).
    # When unset, long-term memory is off and the agent runs on sessions alone.
    database_url: str | None = field(default_factory=lambda: os.getenv("DATABASE_URL") or None)

    @property
    def telemetry_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    def model_label(self) -> str:
        """Human-readable model+endpoint string for self-report."""
        if self.provider == "openai":
            return f"{self.openai_model_id} (OpenAI API)"
        if self.provider == "anthropic":
            return f"{self.anthropic_model_id} (Anthropic API)"
        if self.provider == "vllm":
            return f"{self.vllm_model_id} (self-hosted vLLM at {self.vllm_base_url})"
        return f"unknown provider: {self.provider}"


# Module-level singleton; import this everywhere.
settings = Settings()
