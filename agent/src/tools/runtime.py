"""Runtime self-report tool: which model and endpoint the agent runs on.

Read-only. Surfaces the configured provider from settings so the agent reports
its real model and endpoint instead of guessing. Region and time are covered by
deployed_region and the current_time built-in.
"""

from __future__ import annotations

from strands import tool

from config.settings import settings


@tool
def model_endpoint(agent=None) -> str:
    """Report the model, endpoint, and current session this agent is running on.

    Use this when asked what model, provider, endpoint, or session/conversation id
    you are on, so the answer reflects the real runtime rather than a guess.
    Self-hosted inference (vLLM) is reported plainly when that is the provider.

    Returns:
        The provider, model id, endpoint, and the current session id (if any).
    """
    provider = settings.provider
    if provider == "openai":
        endpoint = "OpenAI API (https://api.openai.com/v1)"
        model_id = settings.openai_model_id
    elif provider == "anthropic":
        endpoint = "Anthropic API (https://api.anthropic.com)"
        model_id = settings.anthropic_model_id
    elif provider == "vllm":
        endpoint = f"self-hosted vLLM at {settings.vllm_base_url}"
        model_id = settings.vllm_model_id
    else:
        endpoint = "unknown"
        model_id = "unknown"

    # build_agent stashes the session id in public state when one is active.
    # No session id means in-process memory only (the CLI).
    state = getattr(agent, "state", None)
    session_id = state.get("session_id") if state else None
    if session_id:
        session_line = f"Session id: {session_id} (persisted via {settings.session_backend})"
    else:
        session_line = "Session: in-process memory only (no persistent session id)"

    return "\n".join(
        [
            f"Provider: {provider}",
            f"Model id: {model_id}",
            f"Endpoint: {endpoint}",
            session_line,
        ]
    )
