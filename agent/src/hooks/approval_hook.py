"""The approval gate: deny mutations by default, require a fresh human approval.

This is a BeforeToolCall hook. It runs before every tool call and lets read
tools through untouched. For any tool tagged as a write in tools/registry.py it
denies by default: the call is cancelled and the agent is told the exact planned
change plus a one-time approval token. Nothing on the account is touched.

The approval itself is a discrete step the model cannot self-grant. The grant
arrives out of band, in the agent's invocation_state (set by the API or the CLI
from the human's confirm), never as a tool argument the model controls. A write
runs only when the grant in invocation_state matches the token for that exact
tool and parameters.

Round-trip:
  1. The model calls a write tool. The gate cancels it, records the plan, and
     returns the planned change and token. The agent relays this to the user.
  2. The user approves. The caller re-sends the request with the token in
     invocation_state. The model re-issues the identical call, the token
     matches, and the tool runs.

Destructive writes are off in demo mode. When demo mode is off they still need a
second confirmation flag in invocation_state, so a single approval is never
enough to delete something.
"""

from __future__ import annotations

from typing import Any

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from config.settings import settings
from tools.registry import describe, is_destructive, is_write, plan_token

# Keys the gate reads from invocation_state. The model cannot set these; only
# the caller (API / CLI) injects them from a human confirm.
GRANT_KEY = "_approval_grant"
CONFIRM_KEY = "_confirm_destructive"


class ApprovalGate(HookProvider):
    """Block mutating tools until a matching human approval is presented.

    One gate instance per request. After the agent run, the caller reads
    `pending` (the change awaiting approval, if any) and `executed` (writes that
    actually ran) to drive the approval round-trip and the response.
    """

    def __init__(self, interactive: bool = False) -> None:
        # Interactive (CLI) gates prompt the human inline and resolve in one
        # turn. Non-interactive (HTTP/Discord) gates deny and hand back a token
        # for the caller's approval round-trip. Either way the model cannot
        # self-approve: the decision comes from outside the model.
        self.interactive = interactive
        # The change that was blocked and is awaiting approval, or None.
        self.pending: dict[str, Any] | None = None
        # Names of write tools that actually executed this run.
        self.executed: list[str] = []

    def reset(self) -> None:
        """Clear per-turn state. The CLI reuses one gate across a conversation."""
        self.pending = None
        self.executed = []

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._gate)

    def _prompt_human(self, summary: str, destructive: bool) -> bool:
        """Ask the human to approve a write inline (the CLI handoff layer)."""
        from strands_tools.utils.user_input import get_user_input

        ans = get_user_input(
            f"\nApproval required. Planned change: {summary}\nApprove? [y/N]: "
        ).strip().lower()
        if ans not in ("y", "yes"):
            return False
        if destructive:
            confirm = get_user_input(
                "This is DESTRUCTIVE. Type 'confirm' to proceed: "
            ).strip().lower()
            return confirm == "confirm"
        return True

    def _gate(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]

        # Read tools are never gated.
        if not is_write(name):
            return

        params = event.tool_use.get("input", {}) or {}
        token = plan_token(name, params)
        destructive = is_destructive(name)
        summary = describe(name, params)

        # Destructive ops are off in demo mode in every channel; check before the
        # interactive prompt so a CLI user cannot approve a delete in demo mode.
        if destructive and settings.demo_mode:
            self.pending = {
                "token": token,
                "tool": name,
                "params": params,
                "summary": summary,
                "destructive": True,
                "blocked_reason": "demo_mode",
            }
            event.cancel_tool = (
                f"BLOCKED: '{name}' is a destructive operation and destructive "
                f"operations are disabled in demo mode. Nothing was changed. "
                f"Tell the user this is off in demo mode and was not run. "
                f"Planned change would have been: {summary}"
            )
            return

        # Interactive (CLI): ask the human inline and resolve in this one turn.
        if self.interactive:
            if self._prompt_human(summary, destructive):
                self.executed.append(name)
                return
            self.pending = {
                "token": token,
                "tool": name,
                "params": params,
                "summary": summary,
                "destructive": destructive,
                "blocked_reason": "declined",
            }
            event.cancel_tool = (
                f"The user DECLINED this change. Nothing was changed. "
                f"Tell them it was not done. Planned change was: {summary}"
            )
            return

        inv = event.invocation_state or {}
        granted = inv.get(GRANT_KEY)
        confirmed = bool(inv.get(CONFIRM_KEY))

        approved = (granted == token) and (not destructive or confirmed)
        if approved:
            # Fresh, matching approval present. Let the tool run.
            self.executed.append(name)
            return

        # No valid approval. Deny by default and record the plan for the caller.
        self.pending = {
            "token": token,
            "tool": name,
            "params": params,
            "summary": summary,
            "destructive": destructive,
            "blocked_reason": "needs_approval",
        }

        extra = ""
        if destructive:
            extra = (
                " This is a DESTRUCTIVE operation and needs a second explicit "
                "confirmation in addition to approval."
            )
        event.cancel_tool = (
            f"APPROVAL REQUIRED. Nothing has been changed yet.{extra}\n\n"
            f"Planned change: {summary}\n"
            f"Approval token: {token}\n\n"
            f"Do not call this tool again now. Show the user the planned change "
            f"and the approval token exactly, and ask them to approve. They "
            f"approve by re-sending the request with this approval token."
        )
