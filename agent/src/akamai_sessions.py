"""A Strands session manager for Akamai Object Storage.

Object Storage is S3-compatible, so this is a thin wrapper over Strands'
``S3SessionManager``: give it a cluster (like ``us-sea-1``) and your Object
Storage access keys, and it derives the endpoint and passes the credentials.

There are no ``AWS_*`` environment variables. boto3 is the client because
Object Storage speaks S3, so the only ``aws_`` names are boto3 parameters; the
credentials they carry are your Akamai keys.
"""

from __future__ import annotations

import boto3
from strands.session.s3_session_manager import S3SessionManager


class AkamaiObjectStorageSessionManager(S3SessionManager):
    """Store Strands sessions on Akamai Object Storage."""

    def __init__(self, session_id, bucket, cluster, access_key, secret_key, *, endpoint_url=None, **kwargs):
        # boto3 names these aws_*, but they are your Akamai Object Storage keys.
        akamai = boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        super().__init__(
            session_id=session_id,
            bucket=bucket,
            # The cluster gives both the endpoint host and the region the client reports.
            endpoint_url=endpoint_url or f"https://{cluster}.linodeobjects.com",
            region_name=cluster,
            boto_session=akamai,
            **kwargs,
        )
