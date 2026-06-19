"""Optional long-term memory on Akamai Managed PostgreSQL.

Off unless DATABASE_URL is set. Stores durable facts and preferences per user
(keyed by the session id), loaded back at the start of each turn so the agent
recalls them in later conversations.

This is the minimal relational form: a facts table, no embeddings, load the
user's facts and use them. docs/databases-on-akamai.md covers the pgvector
upgrade for when facts grow large. Every call fails soft: if the database is
unreachable, the agent keeps working without long-term memory.
"""

from __future__ import annotations

import logging

from config.settings import settings

log = logging.getLogger("akamai_sa.memory")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_facts (
    id         BIGSERIAL PRIMARY KEY,
    user_key   TEXT NOT NULL,
    fact       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_facts_user_idx ON agent_facts (user_key);
"""

_schema_ready = False


def enabled() -> bool:
    """True when a database is configured."""
    return bool(settings.database_url)


def _connect():
    import psycopg  # imported lazily so the dependency is only needed when enabled

    return psycopg.connect(settings.database_url)


def ensure_schema() -> None:
    """Create the facts table once per process. Safe to call repeatedly."""
    global _schema_ready
    if not enabled() or _schema_ready:
        return
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(_SCHEMA)
            conn.commit()
        _schema_ready = True
    except Exception as exc:  # noqa: BLE001 - run without long-term memory if it fails
        log.warning("long-term memory schema setup failed: %s", exc)


def get_facts(user_key: str, limit: int = 50) -> list[str]:
    """The user's stored facts, newest first. Empty list if disabled or on error."""
    if not (enabled() and user_key):
        return []
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT fact FROM agent_facts WHERE user_key = %s ORDER BY created_at DESC LIMIT %s",
                (user_key, limit),
            )
            return [row[0] for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        log.warning("long-term memory read failed: %s", exc)
        return []


def add_fact(user_key: str, fact: str) -> bool:
    """Store one durable fact for a user. Returns True on success."""
    if not (enabled() and user_key and fact and fact.strip()):
        return False
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_facts (user_key, fact) VALUES (%s, %s)",
                (user_key, fact.strip()),
            )
            conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("long-term memory write failed: %s", exc)
        return False
