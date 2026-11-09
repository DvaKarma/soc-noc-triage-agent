"""`triage-ingest`: load runbooks into the configured vector store (pgvector in production)."""

from __future__ import annotations

from .config import Settings, build_embedder
from .retrieval import chunk_runbook, load_runbooks
from .retrieval.vector_store import PgVectorStore


def ingest() -> None:
    s = Settings.from_env()
    if not s.database_url:
        raise SystemExit("DATABASE_URL is not set; the in-memory store is rebuilt at startup anyway.")
    store = PgVectorStore(s.database_url, build_embedder(s))
    books = load_runbooks(s.runbooks_dir)
    chunks = [c for b in books.values() for c in chunk_runbook(b)]
    store.add(chunks)
    print(f"ingested {len(chunks)} chunks from {len(books)} runbooks")
