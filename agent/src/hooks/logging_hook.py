"""Logging hook: record tool invocations before they run.

Kept deliberately light so it is safe to run in front of a room. It prints the
tool name and (optionally) the input, but never dumps secrets: token values are
not part of tool inputs, they are read from settings inside each tool.
"""

from __future__ import annotations

import json

from strands.hooks import HookProvider, HookRegistry
from strands.experimental.hooks import BeforeToolInvocationEvent


class LoggingHook(HookProvider):
    """Print a one-line record for every tool invocation."""

    def __init__(self, verbose: bool = True):
        self.calls = 0
        self.verbose = verbose

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolInvocationEvent, self.log_start)

    def log_start(self, event: BeforeToolInvocationEvent) -> None:
        self.calls += 1
        name = event.tool_use["name"]
        if self.verbose:
            try:
                args = json.dumps(event.tool_use.get("input", {}), default=str)
            except Exception:
                args = "<unserializable>"
            print(f"[tool #{self.calls}] {name} {args}")
        else:
            print(f"[tool #{self.calls}] {name}")
