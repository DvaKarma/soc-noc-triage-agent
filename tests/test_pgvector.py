"""Integration test against a real Postgres + pgvector (runs in CI via a service container)."""

import os

import pytest

from triage.retrieval import chunk_runbook
from triage.retrieval.embeddings import HashingEmbedder

DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_pgvector_roundtrip(runbooks):
    from triage.retrieval.vector_store import PgVectorStore

    store = PgVectorStore(DSN, HashingEmbedder(), table="test_chunks")
    store.conn.execute("TRUNCATE test_chunks")
    store.add([c for b in runbooks.values() for c in chunk_runbook(b)])
    hits = store.search("thin pool data usage over 95%", k=3)
    assert hits[0].chunk.runbook_id == "thin-pool-full"
