"""Discord bridge for the Akamai Cloud Solutions Architect agent.

Optional. The bot runs the multi-agent orchestrator, the same agent the HTTP
service serves, so the gate, the tools, and the system prompt behave identically
no matter how the agent is reached.

The approval round-trip is rendered as an interactive confirm. When a write is
planned, the gate denies it by default and returns the exact planned change plus
a one-time token. The bot shows that plan with Approve / Decline buttons. On
Approve it re-invokes with the token in invocation_state (which the model cannot
set), so the same code that protects the HTTP path protects Discord. Destructive
operations, when they are enabled at all, take a second explicit confirmation.

Design split: the pure helpers below (chunking, the invoke/pending->confirm core)
do not import discord, so they can be unit-tested without the discord runtime
installed. `discord` is imported lazily inside `main()`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Callable

from config.settings import settings
from mcp_integration import make_read_mcp_client
from orchestrator import run_turn

log = logging.getLogger("akamai_sa.discord")

# Read tools from the akamai-cloud-mcp server, set once at startup in main().
_read_tools = None


def run_once(message: str, grant: str | None = None, confirm: bool = False):
    """Run one turn through the multi-agent orchestrator with the shared reads."""
    return run_turn(message, read_tools=_read_tools, grant=grant, confirm=confirm)

# Discord hard-caps a message at 2000 chars. Stay under it and prefer newline
# breaks so code blocks and lists do not get cut mid-line.
DISCORD_CHUNK_LIMIT = 1900

# Per-user cooldown so one person cannot spin the agent in a tight loop.
RATE_LIMIT_SECONDS = 5


def chunk_for_discord(text: str, limit: int = DISCORD_CHUNK_LIMIT) -> list[str]:
    """Split a long string into Discord-sized chunks, preferring newline breaks.

    Fence-aware: if a chunk ends inside an open ``` code block, the fence is
    closed at the end of that chunk and reopened with the same language at the
    start of the next. A long Terraform or CLI block stays rendered as code
    across messages instead of breaking at the 2000-char limit.
    """
    text = (text or "").strip()
    if not text:
        return ["(no response)"]

    raw: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        raw.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    raw.append(text)

    # Re-balance code fences across chunk boundaries so split code blocks render.
    chunks: list[str] = []
    carry_lang: str | None = None
    for part in raw:
        if carry_lang is not None:
            part = f"```{carry_lang}\n{part}"
        fences = re.findall(r"^```(\w*)", part, re.M)
        if len(fences) % 2 == 1:  # ends with an unclosed opening fence
            carry_lang = fences[-1]
            part = part + "\n```"
        else:
            carry_lang = None
        chunks.append(part)
    return chunks


def invoke_for_discord(
    message: str,
    grant: str | None = None,
    confirm: bool = False,
    runner: Callable[..., tuple[str, Any]] = run_once,
) -> dict[str, Any]:
    """Run one message through the agent and shape the result for the bridge.

    This is the bot's core, kept free of discord so it can be tested directly.
    Returns a dict with:
      - text:     the agent's response to show the user
      - pending:  the planned change awaiting approval, or None. Present only
                  when a write was blocked and is waiting on a human confirm.
      - executed: write tools that actually ran this turn

    `runner` is injectable for tests; it defaults to the real `run_once`.
    """
    text, gate = runner(message, grant=grant, confirm=confirm)

    pending = None
    if gate.pending and gate.pending.get("blocked_reason") == "needs_approval":
        p = gate.pending
        pending = {
            "token": p["token"],
            "tool": p["tool"],
            "summary": p["summary"],
            "destructive": p["destructive"],
        }

    return {"text": text, "pending": pending, "executed": list(gate.executed)}


def format_approval(pending: dict[str, Any]) -> str:
    """Render a pending change as the confirm prompt shown above the buttons."""
    lines = [
        "**Approval required.** Nothing has been changed yet.",
        "",
        f"**Planned change:** {pending['summary']}",
        f"**Tool:** `{pending['tool']}`",
    ]
    if pending.get("destructive"):
        lines.append(
            "\n:warning: This is a **destructive** operation and needs a second "
            "explicit confirmation."
        )
    lines.append("\nApprove to run it, or Decline to cancel.")
    return "\n".join(lines)


# Match a local image path the diagram tools wrote (e.g. "diagrams/lke-123.png").
_IMAGE_RE = re.compile(r"(?<![\w-])((?:[\w./~-]+/)?[\w.-]+\.(?:png|jpe?g|svg))")


def split_images(text: str) -> tuple[str, list[str]]:
    """Pull local image paths out of a response so the bridge can attach them.

    The model may reference a rendered diagram as a bare path, a "Diagram saved
    to <path>" line, or a markdown image. Discord shows none of those, so find
    the images that exist on disk, return them to upload as attachments, and
    strip every reference to them from the text.
    """
    text = text or ""
    paths: list[str] = []
    seen: set[str] = set()
    for m in _IMAGE_RE.finditer(text):
        p = m.group(1)
        if p not in seen and os.path.isfile(p):
            seen.add(p)
            paths.append(p)
    cleaned = text
    for p in paths:
        esc = re.escape(p)
        cleaned = re.sub(r"!?\[[^\]]*\]\(\s*" + esc + r"\s*\)", "", cleaned)  # markdown image or link
        cleaned = re.sub(r"Diagram saved to\s+" + esc, "", cleaned)          # the diagram tool's phrasing
        cleaned = cleaned.replace(p, "")                                     # any bare path
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if paths and not cleaned:
        cleaned = "Diagram attached below."
    return cleaned, paths


async def _send_chunked(channel, text: str, reply_to=None) -> None:
    """Send text to a channel, chunked, replying to a message for the first part."""
    first = True
    for part in chunk_for_discord(text):
        if first and reply_to is not None:
            await reply_to.reply(part, mention_author=False)
            first = False
        else:
            await channel.send(part)


HELP_TEXT = (
    "**Akamai Cloud Solutions Architect** (a Strands agent running on Akamai Cloud)\n\n"
    "Ask in plain English about Compute, LKE, Object Storage, networking, GPUs, AI "
    "inference, and billing. For example:\n"
    "- list my Linodes and where they are\n"
    "- what does it cost to run 3 GPUs for a month\n"
    "- draw my LKE cluster\n"
    "- give me the Terraform for a Managed PostgreSQL\n"
    "- tag linode 12345 with demo  (then click Approve)\n\n"
    "**Reach me:** `/ask`, `$sa <question>` in a channel, `@mention` me, or DM me.\n"
    "Account changes are approval-gated: I show the exact plan and wait for you to "
    "click Approve."
)


def main() -> None:
    """Run the Discord bot. Requires DISCORD_TOKEN and the `discord` extra."""
    import time

    import discord

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    token = settings.discord_token
    if not token:
        raise RuntimeError(
            "Missing DISCORD_TOKEN. Set it in the environment or the Kubernetes Secret."
        )

    # Open the akamai-cloud-mcp read server once, for the life of the bot, so the
    # orchestrator's account specialist has real read tools.
    global _read_tools
    if settings.mcp_enabled:
        try:
            mcp_client = make_read_mcp_client()
            mcp_client.start()
            _read_tools = mcp_client.list_tools_sync()
            log.info("Reads via akamai-cloud-mcp (%d tools).", len(_read_tools))
        except Exception as exc:  # noqa: BLE001 - bot still runs, reads disabled
            log.warning("akamai-cloud-mcp unavailable: %s; reads disabled.", exc)

    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True
    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)

    rate_limit: dict[str, float] = {}
    start_time = time.monotonic()

    async def deliver(channel, text, reply_to=None):
        """Send the response text (chunked), then upload any diagram images."""
        cleaned, image_paths = split_images(text)
        await _send_chunked(channel, cleaned, reply_to=reply_to)
        if image_paths:
            await channel.send(files=[discord.File(p) for p in image_paths])

    class ApprovalView(discord.ui.View):
        """Approve / Decline buttons bound to one planned change.

        The token rides with the view, never with the model. Approve re-invokes
        `run_once` with the token in invocation_state. Destructive changes (only
        reachable when demo mode is off) take a second confirm step first.
        """

        def __init__(self, question: str, pending: dict[str, Any], requester_id: int):
            super().__init__(timeout=120)
            self.question = question
            self.pending = pending
            self.requester_id = requester_id

        async def _guard(self, interaction: discord.Interaction) -> bool:
            # Only the person who asked may approve their own change.
            if interaction.user.id != self.requester_id:
                await interaction.response.send_message(
                    "Only the requester can approve this change.", ephemeral=True
                )
                return False
            return True

        async def _run_approved(self, interaction: discord.Interaction, confirm: bool) -> None:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            result = await asyncio.to_thread(
                invoke_for_discord,
                self.question,
                grant=self.pending["token"],
                confirm=confirm,
            )
            await deliver(interaction.channel, result["text"])
            self.stop()

        @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
        async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self._guard(interaction):
                return
            if self.pending.get("destructive"):
                # Second explicit confirmation for destructive ops.
                await interaction.response.edit_message(
                    content=(
                        f"{format_approval(self.pending)}\n\n"
                        ":rotating_light: **Confirm destructive action?**"
                    ),
                    view=ConfirmDestructiveView(self.question, self.pending, self.requester_id),
                )
                self.stop()
                return
            await self._run_approved(interaction, confirm=False)

        @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
        async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self._guard(interaction):
                return
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content="Declined. Nothing was changed.", view=self
            )
            self.stop()

    class ConfirmDestructiveView(discord.ui.View):
        """Second-stage confirm for destructive operations."""

        def __init__(self, question: str, pending: dict[str, Any], requester_id: int):
            super().__init__(timeout=120)
            self.question = question
            self.pending = pending
            self.requester_id = requester_id

        @discord.ui.button(label="Confirm destroy", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.requester_id:
                await interaction.response.send_message(
                    "Only the requester can confirm this change.", ephemeral=True
                )
                return
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            result = await asyncio.to_thread(
                invoke_for_discord,
                self.question,
                grant=self.pending["token"],
                confirm=True,
            )
            await deliver(interaction.channel, result["text"])
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.requester_id:
                await interaction.response.send_message(
                    "Only the requester can cancel this change.", ephemeral=True
                )
                return
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content="Cancelled. Nothing was changed.", view=self
            )
            self.stop()

    @tree.command(name="ask", description="Ask the Akamai Cloud Solutions Architect agent")
    @discord.app_commands.describe(question="Your question about Akamai Cloud")
    async def ask_command(interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(invoke_for_discord, question)
        except Exception:
            log.exception("slash /ask failed")
            await interaction.followup.send("Something went wrong. Please try again.")
            return
        cleaned, image_paths = split_images(result["text"])
        for part in chunk_for_discord(cleaned):
            await interaction.followup.send(part)
        if image_paths:
            await interaction.followup.send(files=[discord.File(p) for p in image_paths])
        if result["pending"]:
            view = ApprovalView(question, result["pending"], interaction.user.id)
            await interaction.followup.send(format_approval(result["pending"]), view=view)

    @tree.command(name="help", description="What you can ask the agent")
    async def help_command(interaction: discord.Interaction):
        await interaction.response.send_message(HELP_TEXT, ephemeral=True)

    synced = {"done": False}

    @client.event
    async def on_ready():
        log.info("Logged in as %s | provider %s", client.user, settings.model_label())
        if not synced["done"]:
            try:
                if settings.discord_guild_id:
                    guild = discord.Object(id=int(settings.discord_guild_id))
                    tree.copy_global_to(guild=guild)
                    await tree.sync(guild=guild)
                    log.info("Slash commands synced to guild %s.", settings.discord_guild_id)
                else:
                    await tree.sync()
                    log.info("Slash commands synced globally (can take up to an hour).")
            except Exception:
                log.exception("slash command sync failed")
            synced["done"] = True

    @client.event
    async def on_message(message):
        if client.user is None or message.author == client.user:
            return

        content = (message.content or "").strip()
        if not content:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mention = client.user.mentioned_in(message)
        is_command = content.startswith("$sa")

        if content.startswith("$help") or content.startswith("$about"):
            await message.channel.send(HELP_TEXT)
            return

        if content.startswith("$status"):
            uptime_s = int(time.monotonic() - start_time)
            hours, rem = divmod(uptime_s, 3600)
            mins, _ = divmod(rem, 60)
            await message.channel.send(
                f"```\nUptime:    {hours}h {mins}m\n"
                f"Model:     {settings.model_label()}\n"
                f"Demo mode: {settings.demo_mode}\n```"
            )
            return

        if not (is_dm or is_mention or is_command):
            return

        # Per-user rate limit.
        user_id = str(message.author.id)
        now = time.monotonic()
        if now - rate_limit.get(user_id, 0.0) < RATE_LIMIT_SECONDS:
            await message.channel.send("Slow down a moment, then try again.")
            return
        rate_limit[user_id] = now
        if len(rate_limit) > 500:
            cutoff = now - 60
            for k in [k for k, v in rate_limit.items() if v < cutoff]:
                del rate_limit[k]

        # Extract the question from the trigger.
        question = content
        if is_command:
            question = content[len("$sa"):].strip()
        elif is_mention:
            question = (
                content.replace(f"<@{client.user.id}>", "")
                .replace(f"<@!{client.user.id}>", "")
                .strip(" :,-\n\t")
            )
        if not question:
            await message.channel.send("Ask me about Akamai Cloud after `$sa` or the @mention.")
            return

        # React so you know it saw your message, before the model runs.
        try:
            await message.add_reaction("\N{EYES}")
        except Exception:  # noqa: BLE001 - reactions are best-effort
            pass

        async with message.channel.typing():
            try:
                result = await asyncio.to_thread(invoke_for_discord, question)
            except Exception:
                log.exception("invoke failed")
                await message.channel.send("Something went wrong. Please try again.")
                return

        await deliver(
            message.channel, result["text"], reply_to=None if is_dm else message
        )

        # If a write is waiting on approval, render the interactive confirm.
        if result["pending"]:
            view = ApprovalView(question, result["pending"], message.author.id)
            await message.channel.send(format_approval(result["pending"]), view=view)

    client.run(token)


if __name__ == "__main__":
    main()
