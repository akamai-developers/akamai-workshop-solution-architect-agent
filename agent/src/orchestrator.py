"""The multi-agent form of the agent: an orchestrator that routes to specialists.

This is what the workshop builds up to in Module 7 and ships in Module 8. The orchestrator
is the only user-facing agent. It routes each part of a request to a focused specialist it
calls as a tool (documentation, account, pricing), and keeps the diagram tools, the write
tools, the approval gate, and the session on itself.

One model object backs the orchestrator and every specialist. Specialists are built fresh
per call with callback_handler=None, so only the orchestrator streams. The read tools (the
akamai-cloud-mcp tools) are injected; writes stay gated by the ApprovalGate.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from strands import Agent, tool
from strands_tools import calculator, current_time, think

from config.settings import settings
from hooks import ApprovalGate, LoggingHook
from models import build_model
from sessions import make_session_manager
from telemetry import init_telemetry
from tools.diagrams import diagram_lke_cluster, diagram_network
from tools.config_examples import config_examples
from tools.regions import deployed_region
from tools.runtime import model_endpoint
from tools.writes import (
    create_instance,
    delete_instance,
    resize_instance,
    tag_instance,
    untag_instance,
)

ORCH_NAME = "Akamai Cloud Solutions Architect"
ORCH_DESCRIPTION = (
    "Akamai Cloud Solutions Architect. Helps developers design, build, and run workloads on "
    "Akamai Cloud (Linode): compute, LKE, Object Storage, networking, and GPUs. Routes account, "
    "pricing, and documentation questions to specialists, draws architecture, and gates writes."
)

WRITE_TOOLS = [tag_instance, untag_instance, resize_instance, create_instance, delete_instance]


# ---------------------------------------------------------------- documentation retrieval
# The Akamai Cloud product docs live under these two paths in the llms.txt index.
_ALLOWED = ("https://techdocs.akamai.com/cloud-computing/", "https://techdocs.akamai.com/linode-api/")
_ENTRY = re.compile(r"^- \[(.*?)\]\((https?://[^)]+\.md)\)(?::\s*(.*))?$", re.M)
_STOP = {"how", "the", "do", "to", "my", "in", "on", "of", "and", "or", "for", "is", "are",
         "what", "with", "you", "your", "can", "does", "this", "that", "it", "be", "from",
         "use", "get", "set", "any", "all"}


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _docs_search(question: str, k: int = 3):
    """Score the local index by whole-word overlap, weighting the title higher."""
    if not settings.docs_index_path:
        return []
    try:
        text = open(settings.docs_index_path, encoding="utf-8").read()
    except OSError:
        return []
    qwords = {w for w in _tokens(question) if w not in _STOP and len(w) > 2}
    scored = []
    for m in _ENTRY.finditer(text):
        title, url, desc = m.group(1), m.group(2), (m.group(3) or "")
        if not url.startswith(_ALLOWED):
            continue
        tw, ow = _tokens(title), _tokens(desc + " " + url)
        score = sum((3 if w in tw else 0) + (1 if w in ow else 0) for w in qwords)
        if score:
            scored.append((score, title, url))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]


def _clean_page(markdown: str) -> str:
    i = markdown.find("\n# ")
    return (markdown[i + 1:] if i != -1 else markdown).strip()


@tool
def docs_lookup(question: str) -> str:
    """Find and read the Akamai Cloud doc pages that answer a question.

    Searches the local docs index, then fetches the top matching pages live from
    techdocs.akamai.com and returns their text with source URLs.

    Args:
        question: An Akamai Cloud product or best-practices question.
    Returns:
        The matching doc pages' text, each with its source URL.
    """
    hits = _docs_search(question, 3)
    if not hits:
        return "No matching Akamai Cloud docs page was found (the docs index may be unset)."
    parts = []
    for _score, title, url in hits:
        try:
            body = _clean_page(httpx.get(url, timeout=20, follow_redirects=True).text)[:2000]
        except Exception as exc:  # noqa: BLE001
            body = f"(could not fetch this page: {exc})"
        parts.append(f"## {title}\nSource: {url}\n\n{body}")
    return "\n\n---\n\n".join(parts)


DOCS_PROMPT = (
    "You are an Akamai Cloud documentation and configuration specialist. Akamai Cloud is the Linode "
    "platform: Linode and Akamai Cloud are the same thing, and the docs live at techdocs.akamai.com. "
    "Use docs_lookup to ground answers in the official docs: quote the page and always include the "
    "real source URL. If the user asks for a link, give the actual techdocs.akamai.com URL, never a "
    "generic 'visit the documentation'. When the user asks how to set something up, give concrete "
    "numbered steps. When they want to automate it, call config_examples for the resource and return "
    "the Terraform and the Linode CLI as fenced code blocks (```hcl and ```bash) with the source URL. "
    "Label generated config as a starting point to confirm before applying. Do not invent attributes. "
    "If the docs do not cover it, say so. No em-dashes."
)
ACCOUNT_PROMPT = (
    "You are an Akamai Cloud account specialist. Use your read tools to report real facts: "
    "inventory, region and GPU availability, and catalog prices exactly as the tools return them "
    "(both hourly and monthly). Do not multiply, total, or recommend. If a value is missing, say "
    "so. No em-dashes."
)
PRICING_PROMPT = (
    "You are a cost analyst for Akamai Cloud. The prices and counts you need are in the request. "
    "Do the math with the calculator. A month is 730 hours. Show the per-item cost and the total, "
    "hourly and monthly. State your assumptions. Never invent a price. If a number is missing, say "
    "which one. No em-dashes."
)


def _router_prompt(today: str) -> str:
    return (
        f"# Today\nToday is {today}. Answer date questions from this line, in plain words.\n\n"
        "You are an Akamai Cloud Solutions Architect that coordinates specialists. You do not "
        "answer account, pricing, or documentation questions from your own knowledge. Route each "
        "part of the request to the right specialist, then combine their answers.\n\n"
        "# Specialists (call them as tools)\n"
        "- documentation_agent: Akamai product facts, best practices, and how-to configuration including Terraform and Linode CLI examples.\n"
        "- account_agent: real account data and catalog prices (look-ups only).\n"
        "- pricing_agent: cost math, totals, monthly projections, recommendations.\n\n"
        "# Your own tools\n"
        "- diagram_lke_cluster, diagram_network: draw real architecture in one call; show the path and summary.\n"
        "- current_time, model_endpoint, deployed_region: self-report, do not guess.\n"
        "- Write tools (tag, untag, resize, create, delete) change the account and are approval gated. "
        "Always call the tool; never approve in prose. Relay the planned change and the token, then stop.\n\n"
        "# Rules\n"
        "- Akamai Cloud IS the Linode platform. Linode and Akamai Cloud are the same thing. Never tell "
        "the user that Linode is separate from Akamai Cloud or run by a different company. The docs live "
        "at techdocs.akamai.com.\n"
        "- Send every documentation, how-to, 'learn more', or 'give me a link' question to "
        "documentation_agent. It returns the answer with real source URLs. Do not answer these from your "
        "own knowledge, and never say 'visit the official documentation' without the actual link.\n"
        "- For any cost total, FIRST get the per-unit price from account_agent, THEN give those numbers "
        "to pricing_agent. Never ask pricing_agent to look up a price.\n"
        "- Use one specialist per step, in order, then write one combined answer.\n"
        "- In scope: Akamai Cloud compute, LKE, Object Storage, networking, GPUs, billing. CDN, security, "
        "and edge are out of scope; say so in one line and do not improvise.\n"
        "- No em-dashes."
    )


def build_orchestrator(
    read_tools=None,
    *,
    session_id: str | None = None,
    approval: ApprovalGate | None = None,
    verbose: bool = False,
) -> Agent:
    """Build the orchestrator. One shared model backs it and every specialist."""
    init_telemetry()  # Langfuse tracing, enabled when the keys are set.
    gate = approval if approval is not None else ApprovalGate()
    model = build_model()
    reads = list(read_tools) if read_tools else []

    @tool
    def documentation_agent(question: str) -> str:
        """Answer Akamai Cloud product and best-practice questions from the official docs."""
        spec = Agent(model=model, system_prompt=DOCS_PROMPT, tools=[docs_lookup, config_examples], callback_handler=None)
        return str(spec(question))

    @tool
    def account_agent(question: str) -> str:
        """Read-only Akamai Cloud account facts and catalog prices."""
        spec = Agent(model=model, system_prompt=ACCOUNT_PROMPT, tools=reads + [think], callback_handler=None)
        return str(spec(question))

    @tool
    def pricing_agent(task: str) -> str:
        """Cost math: totals, monthly projections, comparisons. Give it the prices and counts."""
        spec = Agent(model=model, system_prompt=PRICING_PROMPT, tools=[calculator, think], callback_handler=None)
        return str(spec(task))

    tools = [
        documentation_agent, account_agent, pricing_agent,
        diagram_lke_cluster, diagram_network,
        current_time, model_endpoint, deployed_region, think,
    ] + WRITE_TOOLS

    today = datetime.now().astimezone().strftime("%A, %B %d, %Y")
    return Agent(
        model=model,
        system_prompt=_router_prompt(today),
        tools=tools,
        hooks=[LoggingHook(verbose=verbose), gate],
        session_manager=make_session_manager(session_id),
        name=ORCH_NAME,
        description=ORCH_DESCRIPTION,
        # No streaming callback. Callers consume the returned text (HTTP, Discord)
        # or print it once (the local REPL). The default handler streams to stdout,
        # which double-prints in the REPL.
        callback_handler=None,
    )


def run_turn(
    message: str,
    *,
    read_tools=None,
    session_id: str | None = None,
    grant: str | None = None,
    confirm: bool = False,
    verbose: bool = False,
):
    """Run one message through a fresh per-request orchestrator and gate.

    Returns (text, gate). The grant and confirm flags travel in invocation_state, never as
    tool arguments, so the model cannot self-approve a write. Mirrors agent.run_turn so the
    HTTP service uses one approval round-trip whichever agent it serves.
    """
    from hooks import CONFIRM_KEY, GRANT_KEY

    gate = ApprovalGate()
    agent = build_orchestrator(read_tools=read_tools, session_id=session_id, approval=gate, verbose=verbose)

    prompt = message
    if grant:
        note = f"\n\n[The user has APPROVED the previously planned change (approval token {grant})."
        if confirm:
            note += " The destructive action is also explicitly confirmed."
        note += " This is the approved re-send. Call the write tool now and report the result.]"
        prompt = message + note

    inv: dict[str, object] = {}
    if grant:
        inv[GRANT_KEY] = grant
    if confirm:
        inv[CONFIRM_KEY] = True
    result = agent(prompt, invocation_state=inv)
    return str(result), gate


def main() -> None:
    """Local chat loop for the multi-agent orchestrator.

    Builds one orchestrator and reuses it, so it remembers within the run. Reads
    come from the akamai-cloud-mcp server kept open around the loop. Writes are
    gated and approved inline. Run it with: python -m orchestrator
    """
    from telemetry import flush_telemetry

    print(f"\n{ORCH_NAME} (multi-agent: orchestrator plus specialists)")
    print(f"Provider: {settings.model_label()}")
    print("Type 'exit' to quit.\n")

    mcp_client = None
    read_tools = None
    if settings.mcp_enabled:
        try:
            from mcp_integration import make_read_mcp_client

            mcp_client = make_read_mcp_client()
            mcp_client.start()
            read_tools = mcp_client.list_tools_sync()
            print(f"Reads via akamai-cloud-mcp ({len(read_tools)} tools).\n")
        except Exception as exc:  # noqa: BLE001 - chat still runs, reads disabled
            print(f"[akamai-cloud-mcp unavailable: {exc}. Reads disabled.]\n")
            mcp_client = None

    try:
        agent = build_orchestrator(
            read_tools=read_tools, approval=ApprovalGate(interactive=True), verbose=True
        )
        while True:
            try:
                prompt = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not prompt:
                continue
            if prompt in ("exit", "quit"):
                break
            print(f"\n{agent(prompt)}\n")
    finally:
        if mcp_client is not None:
            mcp_client.stop(None, None, None)
        flush_telemetry()


if __name__ == "__main__":
    main()
