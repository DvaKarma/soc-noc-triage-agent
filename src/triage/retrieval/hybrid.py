"""Hybrid retrieval: BM25 + dense vectors fused with Reciprocal Rank Fusion (RRF).

Lexical search is strong on exact identifiers (rule ids, item keys, event ids); dense search
handles paraphrases. RRF combines rankings without having to calibrate their raw scores.
"""

from __future__ import annotations

from ..models import Chunk, Hit
from .bm25 import BM25Index
from .vector_store import VectorStore


class HybridRetriever:
    def __init__(self, vector_store: VectorStore, rrf_k: int = 60, candidates: int = 20) -> None:
        self.bm25 = BM25Index()
        self.vectors = vector_store
        self.rrf_k = rrf_k
        self.candidates = candidates

    def add(self, chunks: list[Chunk]) -> None:
        self.bm25.add(chunks)
        self.vectors.add(chunks)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        fused: dict[str, float] = {}
        by_id: dict[str, Chunk] = {}
        for ranking in (
            self.bm25.search(query, self.candidates),
            self.vectors.search(query, self.candidates),
        ):
            for rank, hit in enumerate(ranking):
                by_id[hit.chunk.id] = hit.chunk
                fused[hit.chunk.id] = fused.get(hit.chunk.id, 0.0) + 1.0 / (self.rrf_k + rank + 1)
        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [Hit(chunk=by_id[cid], score=score) for cid, score in ordered]

    def rank_runbooks(self, query: str, k: int = 3) -> list[tuple[str, float, list[Hit]]]:
        """Aggregate chunk hits per runbook (sum of fused scores), best first."""
        hits = self.search(query, k=self.candidates)
        grouped: dict[str, list[Hit]] = {}
        for hit in hits:
            grouped.setdefault(hit.chunk.runbook_id, []).append(hit)
        ranked = sorted(
            ((rb, sum(h.score for h in hs), hs) for rb, hs in grouped.items()),
            key=lambda t: t[1],
            reverse=True,
        )
        return ranked[:k]
