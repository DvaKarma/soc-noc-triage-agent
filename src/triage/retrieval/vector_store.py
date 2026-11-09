"""Vector stores: in-memory (tests, small deployments) and PostgreSQL + pgvector."""

from __future__ import annotations

from typing import Protocol

from ..db import schema_lock
from ..models import Chunk, Hit
from .embeddings import Embedder


class VectorStore(Protocol):
    def add(self, chunks: list[Chunk]) -> None: ...

    def search(self, query: str, k: int = 5) -> list[Hit]: ...


class InMemoryVectorStore:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.items: list[tuple[Chunk, list[float]]] = []

    def add(self, chunks: list[Chunk]) -> None:
        vectors = self.embedder.embed([c.text for c in chunks])
        self.items.extend(zip(chunks, vectors, strict=True))

    def search(self, query: str, k: int = 5) -> list[Hit]:
        (q,) = self.embedder.embed([query])
        hits = [Hit(chunk=c, score=sum(a * b for a, b in zip(q, v, strict=True))) for c, v in self.items]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]


class PgVectorStore:
    """Chunks live in Postgres with the pgvector extension (cosine distance, HNSW index)."""

    def __init__(self, dsn: str, embedder: Embedder, table: str = "runbook_chunks") -> None:
        import psycopg  # optional dependency: pip install .[postgres]

        self.embedder = embedder
        self.table = table
        self.conn = psycopg.connect(dsn, autocommit=True)
        with schema_lock(self.conn):
            self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {table} (
                    id text PRIMARY KEY, runbook_id text NOT NULL, heading text NOT NULL,
                    content text NOT NULL, embedding vector({embedder.dim}) NOT NULL)"""
            )
            self.conn.execute(
                f"CREATE INDEX IF NOT EXISTS {table}_hnsw ON {table} USING hnsw (embedding vector_cosine_ops)"
            )

    @staticmethod
    def _literal(vec: list[float]) -> str:
        return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"

    def add(self, chunks: list[Chunk]) -> None:
        vectors = self.embedder.embed([c.text for c in chunks])
        with schema_lock(self.conn), self.conn.cursor() as cur:
            for chunk, vec in zip(chunks, vectors, strict=True):
                cur.execute(
                    f"""INSERT INTO {self.table} (id, runbook_id, heading, content, embedding)
                        VALUES (%s, %s, %s, %s, %s::vector)
                        ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content,
                        heading = EXCLUDED.heading, embedding = EXCLUDED.embedding""",
                    (chunk.id, chunk.runbook_id, chunk.heading, chunk.text, self._literal(vec)),
                )

    def search(self, query: str, k: int = 5) -> list[Hit]:
        (q,) = self.embedder.embed([query])
        rows = self.conn.execute(
            f"""SELECT id, runbook_id, heading, content, 1 - (embedding <=> %s::vector) AS score
                FROM {self.table} ORDER BY embedding <=> %s::vector LIMIT %s""",
            (self._literal(q), self._literal(q), k),
        ).fetchall()
        return [
            Hit(chunk=Chunk(id=r[0], runbook_id=r[1], heading=r[2], text=r[3]), score=float(r[4]))
            for r in rows
        ]
