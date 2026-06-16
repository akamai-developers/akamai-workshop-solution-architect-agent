"""Tool registry: which tools mutate the account and which are destructive.

This is the single source of truth the approval hook reads. A tool name listed
in WRITE_TOOLS is gated: it does not run without a fresh, explicit human
approval. A name also in DESTRUCTIVE_TOOLS is off in demo mode and, when
enabled, needs a second confirmation.

Keeping the tags here (not on the tools themselves) means the gate cannot be
bypassed by how a tool is written, and the read tools never touch this file.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Mutating tools. Every name here is approval-gated by the hook.
WRITE_TOOLS: set[str] = {
    "tag_instance",
    "untag_instance",
    "resize_instance",
    "create_instance",
    "delete_instance",
}

# Subset of WRITE_TOOLS that destroys resources. Off in demo mode; when enabled
# these require a second explicit confirmation.
DESTRUCTIVE_TOOLS: set[str] = {
    "delete_instance",
}


def is_write(name: str) -> bool:
    return name in WRITE_TOOLS


def is_destructive(name: str) -> bool:
    return name in DESTRUCTIVE_TOOLS


def plan_token(name: str, params: dict[str, Any]) -> str:
    """A short, deterministic token binding an approval to one exact change.

    Same tool plus same parameters always yields the same token, so a follow-up
    request that re-issues the identical call can be matched and approved. Any
    change to the parameters yields a different token, so an approval can never
    be reused for a different action.
    """
    blob = name + "|" + json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def describe(name: str, params: dict[str, Any]) -> str:
    """A one-line, human-readable summary of the planned change.

    Never includes secrets: write tools take only non-sensitive parameters
    (root passwords and similar are generated inside the tool, not passed in).
    """
    p = params or {}
    if name == "tag_instance":
        return f"Add tag '{p.get('tag')}' to Linode {p.get('linode_id')}."
    if name == "untag_instance":
        return f"Remove tag '{p.get('tag')}' from Linode {p.get('linode_id')}."
    if name == "resize_instance":
        return f"Resize Linode {p.get('linode_id')} to plan '{p.get('plan_id')}'."
    if name == "create_instance":
        return (
            f"Create a new Linode: plan '{p.get('plan_id')}' in region "
            f"'{p.get('region')}', image '{p.get('image', 'linode/debian12')}', "
            f"label '{p.get('label')}'."
        )
    if name == "delete_instance":
        return f"DELETE Linode {p.get('linode_id')}. This is irreversible."
    # Fallback for any future write tool.
    return f"{name} with parameters {json.dumps(p, sort_keys=True, default=str)}."
