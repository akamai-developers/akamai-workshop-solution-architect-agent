"""Conversation persistence, selected by SESSION_BACKEND.

Three layers of "remembering", same idea with different storage:

- memory: no session manager. One reused Agent remembers within a process
  (the CLI loop). History is gone when the process exits.
- file:   FileSessionManager on a local or mounted volume. Survives a restart
  on a single replica.
- s3:     AkamaiObjectStorageSessionManager pointed at Akamai Object Storage
  (S3-compatible). Survives restarts and is shared across replicas, so any LKE
  pod behind the NodeBalancer can rehydrate the same conversation by id.

A session manager is bound to one session_id, so callers build a fresh,
session-bound agent per request and let it rehydrate. With no session_id we
return None and rely on in-process memory.
"""

from __future__ import annotations

from config.settings import settings


def make_session_manager(session_id: str | None):
    """Return a SessionManager for this session_id, or None for in-process memory."""
    if not session_id:
        return None

    backend = settings.session_backend
    if backend == "memory":
        return None

    if backend == "file":
        from strands.session.file_session_manager import FileSessionManager

        return FileSessionManager(session_id=session_id, storage_dir=settings.session_dir)

    if backend == "s3":
        from akamai_sessions import AkamaiObjectStorageSessionManager

        if not settings.session_bucket:
            raise ValueError(
                "SESSION_BACKEND=s3 requires SESSION_BUCKET (the Akamai Object Storage bucket)."
            )
        if not (settings.session_cluster and settings.session_access_key and settings.session_secret_key):
            raise ValueError(
                "SESSION_BACKEND=s3 requires SESSION_CLUSTER, SESSION_ACCESS_KEY, and SESSION_SECRET_KEY."
            )
        return AkamaiObjectStorageSessionManager(
            session_id=session_id,
            bucket=settings.session_bucket,
            cluster=settings.session_cluster,
            access_key=settings.session_access_key,
            secret_key=settings.session_secret_key,
            prefix=settings.session_prefix,
            endpoint_url=settings.session_endpoint_url,
        )

    raise ValueError(f"Unknown SESSION_BACKEND '{backend}'. Use memory | file | s3.")
