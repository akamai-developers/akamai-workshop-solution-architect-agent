# Module 3: Guardrails, approval before any change

**Goal:** let the agent make changes, but never without a human approving the exact
action first.

**The problem you will see:** an agent that can call a write tool can delete a Linode
on its own. That is unacceptable in production.

**What you will learn:** a deny-by-default approval gate implemented as a
`BeforeToolCallEvent` hook, the difference between *enforcement* (a structural gate the
model cannot bypass) and *interaction* (how the human is asked), and why the grant must
travel out of band so the model cannot self-approve.

## Planned sections (raw, then framework)
1. Setup
2. A write tool with no guardrail (show the danger on a safe, tagged example)
3. The approval gate by hand: intercept the call, deny by default, return the planned change plus a one-time token
4. The approval round-trip: re-send with the token in `invocation_state`
5. The same with the Strands hook (`ApprovalGate`) wired into the agent
6. Interactive approval for the CLI vs the token round-trip for HTTP and Discord
7. Demo mode and destructive operations (off by default)
8. Things to know (enforcement vs interaction, why the token is bound to the exact params)

## Needs
- A `LINODE_TOKEN` (writes stay in demo mode; nothing destructive runs)

## Files
- `03_guardrails.ipynb`
- `architecture.html` — rendered to `../images/03_guardrails_architecture.png`

_Status: scaffolded._
