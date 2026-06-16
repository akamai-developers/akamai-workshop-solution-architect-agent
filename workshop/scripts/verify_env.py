"""Verify the workshop environment before you start.

Checks Python, that your model endpoint is reachable and serving the model, and
that tool calling actually works. The last check is the one people miss: vLLM
only emits structured tool calls when it is started with the right flags.

Run from the repo root:
    python workshop/scripts/verify_env.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    ok = True

    if sys.version_info < (3, 11):
        print(f"[x] Python 3.11+ required (found {sys.version.split()[0]})")
        ok = False
    else:
        print(f"[ok] Python {sys.version.split()[0]}")

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        print("[!] python-dotenv not installed; reading os.environ only")

    base = os.getenv("VLLM_BASE_URL")
    model = os.getenv("VLLM_MODEL_ID")
    key = os.getenv("VLLM_API_KEY", "placeholder")
    if not base or not model:
        print("[x] Set VLLM_BASE_URL and VLLM_MODEL_ID in .env (copy .env.example).")
        return 1
    print(f"[ok] Endpoint {base}  model {model}")

    try:
        import httpx
    except Exception:
        print("[x] httpx not installed. Run: pip install httpx")
        return 1

    headers = {"Authorization": f"Bearer {key}"}
    root = base.rstrip("/")

    # Reachable and serving the model?
    try:
        resp = httpx.get(f"{root}/models", headers=headers, timeout=10)
        resp.raise_for_status()
        served = [m.get("id") for m in resp.json().get("data", [])]
        if model in served:
            print("[ok] Endpoint is serving the model")
        else:
            print(f"[!] {model} not in served models: {served}")
            ok = False
    except Exception as exc:
        print(f"[x] Could not reach {root}: {exc}")
        return 1

    # Does tool calling actually work?
    probe = {
        "model": model,
        "messages": [{"role": "user", "content": "What is 2 + 2? Use the add tool."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two numbers.",
                    "parameters": {
                        "type": "object",
                        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                        "required": ["a", "b"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
        "max_tokens": 64,
    }
    try:
        resp = httpx.post(f"{root}/chat/completions", headers=headers, json=probe, timeout=30)
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        if message.get("tool_calls"):
            print("[ok] Tool calling works (server returns structured tool_calls)")
        else:
            print(
                "[x] No tool_calls returned. Start vLLM with tool calling enabled, e.g.\n"
                "    vllm serve <model> --enable-auto-tool-choice --tool-call-parser hermes"
            )
            ok = False
    except Exception as exc:
        print(f"[!] Tool-calling probe failed: {exc}")

    print("\nReady. Open workshop/01_first_agent_and_tools.ipynb" if ok else "\nFix the [x] items, then re-run.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
