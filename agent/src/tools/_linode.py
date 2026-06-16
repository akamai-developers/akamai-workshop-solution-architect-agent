"""Shared helpers for talking to the Linode (Akamai Cloud) API.

Centralizes the base URL, auth header, and error handling so every read/write
tool calls the API the same way. The token comes from settings (env / Secret),
never from tool inputs, so it cannot leak into traces or model context.
"""

from __future__ import annotations

from typing import Any

import httpx

from config.settings import settings

LINODE_API = "https://api.linode.com/v4"
METADATA_URL = "http://169.254.169.254/v1/instance"
_TIMEOUT = httpx.Timeout(15.0)


def _headers() -> dict[str, str]:
    if not settings.linode_token:
        raise RuntimeError("LINODE_TOKEN is not set; cannot call the Akamai Cloud API.")
    return {"Authorization": f"Bearer {settings.linode_token}"}


def get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a Linode API path (for example '/regions') and return parsed JSON."""
    url = f"{LINODE_API}{path}"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


def get_all(path: str, params: dict[str, Any] | None = None, max_pages: int = 10) -> list[dict[str, Any]]:
    """GET a paginated Linode collection and return all 'data' items."""
    items: list[dict[str, Any]] = []
    page = 1
    params = dict(params or {})
    with httpx.Client(timeout=_TIMEOUT) as client:
        while page <= max_pages:
            params["page"] = page
            resp = client.get(f"{LINODE_API}{path}", headers=_headers(), params=params)
            resp.raise_for_status()
            body = resp.json()
            items.extend(body.get("data", []))
            if page >= body.get("pages", 1):
                break
            page += 1
    return items


def post(path: str, json_body: dict[str, Any]) -> dict[str, Any]:
    """POST to a Linode API path. Used only by approval-gated write tools."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(f"{LINODE_API}{path}", headers=_headers(), json=json_body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}


def put(path: str, json_body: dict[str, Any]) -> dict[str, Any]:
    """PUT to a Linode API path. Used only by approval-gated write tools."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.put(f"{LINODE_API}{path}", headers=_headers(), json=json_body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}


def delete(path: str) -> dict[str, Any]:
    """DELETE a Linode API path. Used only by approval-gated write tools."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.delete(f"{LINODE_API}{path}", headers=_headers())
        resp.raise_for_status()
        return {"status": "deleted", "path": path}


def metadata_region() -> str | None:
    """Read this node's region from the Linode Metadata Service.

    Returns the region slug (for example 'us-ord') when running on an Akamai
    Cloud instance, or None when the service is not reachable.
    """
    try:
        with httpx.Client(timeout=httpx.Timeout(2.0)) as client:
            resp = client.get(METADATA_URL, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json().get("region")
    except Exception:
        return None
