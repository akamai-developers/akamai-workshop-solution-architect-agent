"""Provision an Akamai Object Storage bucket and a scoped access key for Module 4.

If a bucket with the given name already exists, it is reused (no second bucket is made).
Otherwise it is created. Then an access key is issued that is *limited to this one bucket*
(read and write), so a leaked key cannot touch the rest of your account. Finally the env vars
to paste into your .env are printed, so section 7 of the notebook can store sessions on
Object Storage.

This creates a REAL, billed resource. Remove it with scripts/delete_bucket.py when done.

Usage (from the repo root, with LINODE_TOKEN in your .env):
    python workshop/04_memory_and_sessions/scripts/create_bucket.py
    python workshop/04_memory_and_sessions/scripts/create_bucket.py --region us-ord --label my-sessions
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
    parser.add_argument("--region", default=os.getenv("OBJ_REGION", "us-sea"),
                        help="Object Storage region, for example us-sea or us-ord")
    parser.add_argument("--label", default=os.getenv("SESSION_BUCKET") or "akamai-sa-agent-sessions",
                        help="bucket name (must be globally unique)")
    args = parser.parse_args()

    token = os.getenv("LINODE_TOKEN")
    if not token:
        print("Set LINODE_TOKEN in your .env first.")
        return 1

    region, label = args.region, args.label
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(base_url=API, headers=headers, timeout=40) as client:
        # 1) Bucket, idempotent. Reuse it if a bucket with this name already exists.
        existing = next(
            (b for b in client.get("/object-storage/buckets").json().get("data", []) if b.get("label") == label),
            None,
        )
        if existing:
            hostname = existing["hostname"]
            bucket_region = existing.get("region") or region
            print(f"Bucket '{label}' already exists ({hostname}); reusing it.")
        else:
            resp = client.post("/object-storage/buckets", json={"label": label, "region": region})
            if resp.status_code >= 400:
                print(f"Could not create the bucket: {resp.status_code} {resp.text}")
                return 1
            created = resp.json()
            hostname = created["hostname"]
            bucket_region = created.get("region") or region
            print(f"Created bucket '{label}' ({hostname}).")

        # The cluster is the host segment after the bucket name:
        #   <label>.<cluster>.linodeobjects.com  ->  cluster, e.g. us-sea-1
        cluster = hostname.split(".")[1]

        # 2) A scoped access key: limited to THIS bucket, read and write. Least privilege,
        #    so a leak cannot reach other buckets. The secret is returned only once.
        resp = client.post("/object-storage/keys", json={
            "label": f"{label}-key",
            "bucket_access": [{"region": bucket_region, "bucket_name": label, "permissions": "read_write"}],
        })
        if resp.status_code >= 400:
            print(f"Could not create an access key: {resp.status_code} {resp.text}")
            return 1
        key = resp.json()

    print("\nAdd these to your .env, then re-run section 7 of the notebook:\n")
    print(f"SESSION_BUCKET={label}")
    print(f"SESSION_CLUSTER={cluster}")
    print(f"SESSION_ACCESS_KEY={key['access_key']}")
    print(f"SESSION_SECRET_KEY={key['secret_key']}")
    print(f"\nThis key is limited to the '{label}' bucket (read/write).")
    print("This bucket is billed until you delete it (scripts/delete_bucket.py or the Cloud Manager).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
