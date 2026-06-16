"""FastAPI service that wraps the agent over HTTP.

Endpoints:
  POST /invoke   -> run the agent on a message, return a structured response
  GET  /tools    -> list loaded tools and their descriptions
  GET  /healthz  -> liveness/readiness probe

The Discord bridge calls /invoke internally, so this is the one invoke path.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from orchestrator import ORCH_NAME as AGENT_NAME, build_orchestrator, run_turn
from config.settings import settings
from telemetry import flush_telemetry

log = logging.getLogger("akamai_sa.api")


class InvokeRequest(BaseModel):
    message: str = Field(..., description="The developer's question or instruction.")
    session_id: str | None = Field(
        default=None,
        description=(
            "Conversation id. Re-send the same id to continue the same conversation. "
            "Durable across restarts and replicas when SESSION_BACKEND is file or s3; "
            "in-memory only otherwise."
        ),
    )
    approve: str | None = Field(
        default=None,
        description=(
            "Approval token for a previously planned change. Re-send the original "
            "message with this token to approve the write. The model cannot set it."
        ),
    )
    confirm_destructive: bool = Field(
        default=False,
        description="Second confirmation required for destructive writes when they are enabled.",
    )


class PendingApproval(BaseModel):
    token: str
    tool: str
    summary: str
    destructive: bool
    blocked_reason: str


class InvokeResponse(BaseModel):
    response: str
    model: str
    provider: str
    # Echoes the conversation id so the caller can keep continuing it.
    session_id: str | None = None
    # Present only when a write was planned but not yet approved.
    pending_approval: PendingApproval | None = None
    # Write tools that actually executed this request.
    executed: list[str] = Field(default_factory=list)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open the akamai-cloud-mcp read server once and keep it open for the life of
    # the process; its tools work only while the client is started. Each request
    # builds a session-bound agent from these read tools, so any replica can
    # serve any session.
    app.state.mcp_client = None
    app.state.read_tools = None
    if settings.mcp_enabled:
        try:
            from mcp_integration import make_read_mcp_client

            client = make_read_mcp_client()
            client.start()
            app.state.mcp_client = client
            app.state.read_tools = client.list_tools_sync()
            log.info("Reads via akamai-cloud-mcp (%d tools).", len(app.state.read_tools))
        except Exception as exc:  # noqa: BLE001 - fall back to local reads, do not crash
            log.warning("akamai-cloud-mcp unavailable: %s; using local read tools.", exc)

    # A representative agent for /tools listing (session-less).
    app.state.agent = build_orchestrator(read_tools=app.state.read_tools, verbose=False)
    try:
        yield
    finally:
        if app.state.mcp_client is not None:
            app.state.mcp_client.stop(None, None, None)
        flush_telemetry()


app = FastAPI(title=AGENT_NAME, version="0.1.0", lifespan=lifespan)


def _tool_descriptions(agent) -> list[dict[str, str]]:
    """Best-effort (name, description) for each loaded tool."""
    out: list[dict[str, str]] = []
    registry = getattr(getattr(agent, "tool_registry", None), "registry", {}) or {}
    for name in agent.tool_names:
        desc = ""
        tool = registry.get(name)
        if tool is not None:
            try:
                desc = (tool.tool_spec or {}).get("description", "") or ""
            except Exception:
                desc = ""
        out.append({"name": name, "description": desc.strip()})
    return out


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools")
def tools() -> dict[str, object]:
    agent = app.state.agent
    return {"count": len(agent.tool_names), "tools": _tool_descriptions(agent)}


@app.post("/invoke", response_model=InvokeResponse)
def invoke(req: InvokeRequest) -> InvokeResponse:
    # Per-request agent and gate. Memory comes from the session backend keyed by
    # session_id (rehydrated each request), not from a shared in-process agent,
    # so the service stays horizontally scalable behind the NodeBalancer.
    #
    # Approval round-trip: a write tool is denied by default. The first call
    # returns a pending_approval (the exact planned change plus a token). The
    # caller re-sends the same message (and session_id) with `approve` set to
    # that token to run it. The grant travels in invocation_state, not as a tool
    # argument, so the model cannot self-grant. Destructive writes also need
    # confirm_destructive.
    text, gate = run_turn(
        req.message,
        read_tools=app.state.read_tools,
        session_id=req.session_id,
        grant=req.approve,
        confirm=req.confirm_destructive,
        verbose=False,
    )

    pending = None
    if gate.pending and gate.pending.get("blocked_reason") == "needs_approval":
        pending = PendingApproval(
            token=gate.pending["token"],
            tool=gate.pending["tool"],
            summary=gate.pending["summary"],
            destructive=gate.pending["destructive"],
            blocked_reason=gate.pending["blocked_reason"],
        )

    return InvokeResponse(
        response=text,
        model=settings.model_label(),
        provider=settings.provider,
        session_id=req.session_id,
        pending_approval=pending,
        executed=gate.executed,
    )
