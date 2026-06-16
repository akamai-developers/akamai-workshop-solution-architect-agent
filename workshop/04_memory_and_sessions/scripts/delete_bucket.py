"""Tear down the Module 4 Object Storage bucket and its access keys.

Looks the bucket up by name, deletes it (it must be empty first), and revokes the matching
access key, so the billed resource stops costing you. Run this when you finish the lab.

Usage (from the repo root, with LINODE_TOKEN in your .env):
    python workshop/04_memory_and_sessions/scripts/delete_bucket.py
    python workshop/04_memory_and_sessions/scripts/delete_bucket.py --label my-sessions
"""

from __future__ import annotations

import argparse
import os

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

API = "https://api.linode.com/v4"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default=os.getenv("SESSION_BUCKET") or "akamai-sa-agent-sessions")
    args = parser.parse_args()

    token = os.getenv("LINODE_TOKEN")
    if not token:
        print("Set LINODE_TOKEN in your .env first.")
        return 1

    label = args.label
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(base_url=API, headers=headers, timeout=40) as client:
        bucket = next(
            (b for b in client.get("/object-storage/buckets").json().get("data", []) if b.get("label") == label),
            None,
        )
        if not bucket:
            print(f"Bucket '{label}' not found (already gone).")
        else:
            # The delete path uses the cluster id, for example us-sea-1.
            cluster = bucket.get("cluster") or bucket.get("region")
            resp = client.delete(f"/object-storage/buckets/{cluster}/{label}")
            if resp.status_code in (200, 204):
                print(f"Deleted bucket '{label}' in {cluster}.")
            else:
                print(f"Could not delete the bucket (it must be empty first): {resp.status_code} {resp.text}")
                print("Empty the bucket in the Cloud Manager, then run this again.")

        # Revoke the access key this lab created.
        for key in client.get("/object-storage/keys").json().get("data", []):
            if key.get("label") == f"{label}-key":
                client.delete(f"/object-storage/keys/{key['id']}")
                print(f"Revoked access key '{key['label']}'.")

    print("\nRemove the SESSION_* lines from your .env if you added them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
