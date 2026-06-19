"""A Strands session manager for Akamai Object Storage.

Object Storage is S3-compatible, so this is a thin wrapper over Strands'
``S3SessionManager``: give it a cluster (like ``us-sea-1``) and your Object
Storage access keys, and it derives the endpoint and passes the credentials.

There are no ``AWS_*`` environment variables. boto3 is the client because
Object Storage speaks S3, so the only ``aws_`` names are boto3 parameters; the
credentials they carry are your Akamai keys.

One S3 client is shared across every session manager. The bridge builds a fresh
session manager per turn, and a new boto3 client per turn churns connections,
which under sustained use fills the pool and drops connections
(``ConnectionClosedError``). A single reused client pools connections and retries
transient drops.
"""

from __future__ import annotations

import boto3
from botocore.config import Config as BotocoreConfig
from strands.session.s3_session_manager import S3SessionManager

# Process-wide S3 client, keyed by the connection config so a credential change
# rebuilds it. Reused by every AkamaiObjectStorageSessionManager instance.
_client = None
_client_key: tuple | None = None


def _shared_s3_client(cluster: str, access_key: str, secret_key: str, endpoint_url: str):
    """Return one pooled, retrying S3 client, building it once per config."""
    global _client, _client_key
    key = (cluster, access_key, endpoint_url)
    if _client is None or _client_key != key:
        _client = boto3.client(
            "s3",
            region_name=cluster,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotocoreConfig(
                max_pool_connections=50,
                retries={"max_attempts": 3, "mode": "standard"},
                user_agent_extra="strands-agents",
            ),
        )
        _client_key = key
    return _client


class AkamaiObjectStorageSessionManager(S3SessionManager):
    """Store Strands sessions on Akamai Object Storage, reusing one pooled client."""

    def __init__(self, session_id, bucket, cluster, access_key, secret_key, *, endpoint_url=None, **kwargs):
        # The cluster gives both the endpoint host and the region the client reports.
        endpoint = endpoint_url or f"https://{cluster}.linodeobjects.com"
        # boto3 names these aws_*, but they are your Akamai Object Storage keys.
        akamai = boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        super().__init__(
            session_id=session_id,
            bucket=bucket,
            endpoint_url=endpoint,
            region_name=cluster,
            boto_session=akamai,
            **kwargs,
        )
        # Replace the per-instance client with the shared, pooled one. The client
        # the parent just built makes no connections (boto3 connects lazily), so
        # swapping it before any request avoids the per-turn connection churn.
        self.client = _shared_s3_client(cluster, access_key, secret_key, endpoint)
