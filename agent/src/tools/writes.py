"""Approval-gated write tools over the Linode (Akamai Cloud) API.

Every tool here mutates the account, so every one is tagged in tools/registry.py
and gated by the approval hook. By the time a function body runs, the gate has
already passed a fresh, matching human approval; these functions just perform
the change and report the result.

The Linode token is read from settings inside the shared client, never passed in
as a tool argument, so it stays out of traces and model context. The same holds
for the root password on create: it is generated here, not accepted as a
parameter, so it never appears in a plan, a trace, or the model's context.
"""

from __future__ import annotations

import secrets

from strands import tool

from tools import _linode


@tool
def tag_instance(linode_id: int, tag: str) -> str:
    """Add a tag to a Linode instance. Approval required.

    Args:
        linode_id: The numeric ID of the Linode to tag.
        tag: The tag to add (for example 'env:test').
    """
    try:
        inst = _linode.get(f"/linode/instances/{linode_id}")
        tags = list(inst.get("tags", []))
        if tag in tags:
            return f"Linode {linode_id} already has tag '{tag}'. No change made."
        tags.append(tag)
        _linode.put(f"/linode/instances/{linode_id}", {"tags": tags})
        return f"Tagged Linode {linode_id} with '{tag}'. Tags are now: {', '.join(tags)}."
    except Exception as e:  # noqa: BLE001
        return f"Failed to tag Linode {linode_id}: {e}"


@tool
def untag_instance(linode_id: int, tag: str) -> str:
    """Remove a tag from a Linode instance. Approval required.

    Args:
        linode_id: The numeric ID of the Linode.
        tag: The tag to remove.
    """
    try:
        inst = _linode.get(f"/linode/instances/{linode_id}")
        tags = list(inst.get("tags", []))
        if tag not in tags:
            return f"Linode {linode_id} does not have tag '{tag}'. No change made."
        tags.remove(tag)
        _linode.put(f"/linode/instances/{linode_id}", {"tags": tags})
        remaining = ", ".join(tags) if tags else "(none)"
        return f"Removed tag '{tag}' from Linode {linode_id}. Tags are now: {remaining}."
    except Exception as e:  # noqa: BLE001
        return f"Failed to untag Linode {linode_id}: {e}"


@tool
def resize_instance(linode_id: int, plan_id: str) -> str:
    """Resize a Linode to a different plan. Approval required. Reboots the Linode.

    Args:
        linode_id: The numeric ID of the Linode to resize.
        plan_id: The target plan type (for example 'g6-standard-4').
    """
    try:
        _linode.post(f"/linode/instances/{linode_id}/resize", {"type": plan_id})
        return f"Resize started: Linode {linode_id} to plan '{plan_id}'. The Linode reboots to apply the change."
    except Exception as e:  # noqa: BLE001
        return f"Failed to resize Linode {linode_id}: {e}"


@tool
def create_instance(region: str, plan_id: str, label: str, image: str = "linode/debian12") -> str:
    """Create a new Linode instance. Approval required. This incurs cost.

    A strong root password is generated server side and is not returned, logged,
    or traced. Reset it through the Cloud Manager or API after the Linode boots.

    Args:
        region: Region slug to deploy in (for example 'us-ord').
        plan_id: The plan type (for example 'g6-nanode-1').
        label: A label for the new Linode.
        image: The image to deploy. Defaults to 'linode/debian12'.
    """
    try:
        body = {
            "region": region,
            "type": plan_id,
            "label": label,
            "image": image,
            # Generated here so it never appears as a tool argument, plan, or trace.
            "root_pass": secrets.token_urlsafe(24),
        }
        created = _linode.post("/linode/instances", body)
        new_id = created.get("id", "unknown")
        return (
            f"Created Linode {new_id} ('{label}', plan '{plan_id}') in {region}. "
            f"Reset the root password via the Cloud Manager before use."
        )
    except Exception as e:  # noqa: BLE001
        return f"Failed to create Linode: {e}"


@tool
def delete_instance(linode_id: int) -> str:
    """Delete a Linode instance. Destructive and irreversible. Approval required.

    Off in demo mode. When enabled, needs a second explicit confirmation.

    Args:
        linode_id: The numeric ID of the Linode to delete.
    """
    try:
        _linode.delete(f"/linode/instances/{linode_id}")
        return f"Deleted Linode {linode_id}."
    except Exception as e:  # noqa: BLE001
        return f"Failed to delete Linode {linode_id}: {e}"
