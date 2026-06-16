"""Optional Langfuse / OpenTelemetry tracing.

Tracing is enabled only when the Langfuse keys are present, so the agent runs
fine without them. With the `strands-agents[otel]` extra installed and the
LANGFUSE_* env set, Strands exports OpenTelemetry traces to Langfuse
automatically; we just initialize and auth-check the client once at startup.

We never put tokens, kubeconfigs, or PII into traces: tool inputs carry only
plain parameters, and credentials are read from settings inside each tool.
"""

from __future__ import annotations

import os

from config.settings import settings

_client = None


def init_telemetry():
    """Initialize Langfuse tracing if configured. Returns the client or None."""
    global _client
    if not settings.telemetry_enabled:
        return None
    if _client is not None:
        return _client

    # The Langfuse SDK and the OTEL exporter read these from the environment.
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key or "")
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key or "")
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)

    try:
        from langfuse import get_client
    except ImportError:
        print("[telemetry] langfuse not installed; install the 'telemetry' extra. Tracing disabled.")
        return None

    client = get_client()
    try:
        if client.auth_check():
            print(f"[telemetry] Langfuse tracing enabled -> {settings.langfuse_host}")
            _client = client
            return client
        print("[telemetry] Langfuse auth_check failed; check keys/host. Tracing disabled.")
    except Exception as e:
        print(f"[telemetry] Langfuse init error: {type(e).__name__}: {e}. Tracing disabled.")
    return None


def flush_telemetry():
    """Flush buffered traces. Call on shutdown (service) or before exit (CLI)."""
    if _client is not None:
        try:
            _client.flush()
        except Exception:
            pass
