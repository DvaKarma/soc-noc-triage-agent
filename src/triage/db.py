"""Postgres helpers shared by the vector store and the triage repository."""

from __future__ import annotations

from contextlib import contextmanager

# Arbitrary constant: every replica takes the same advisory lock before touching the schema,
# so two pods starting together do not race on CREATE EXTENSION / CREATE TABLE.
SCHEMA_LOCK_ID = 7_301_984_221


@contextmanager
def schema_lock(conn):
    conn.execute("SELECT pg_advisory_lock(%s)", (SCHEMA_LOCK_ID,))
    try:
        yield
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (SCHEMA_LOCK_ID,))
