"""Small, dependency-free Okapi BM25 for the lexical half of hybrid search."""

from __future__ import annotations

import math
from collections import Counter

from ..models import Chunk, Hit
from .text import tokenize


class BM25Index:
    def __init__(self, k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.chunks: list[Chunk] = []
        self.tfs: list[Counter[str]] = []
        self.df: Counter[str] = Counter()
        self.avgdl = 0.0

    def add(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            tf = Counter(tokenize(chunk.text))
            self.chunks.append(chunk)
            self.tfs.append(tf)
            self.df.update(tf.keys())
        self.avgdl = sum(sum(tf.values()) for tf in self.tfs) / max(len(self.tfs), 1)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        terms = tokenize(query)
        n = len(self.chunks)
        scored: list[Hit] = []
        for chunk, tf in zip(self.chunks, self.tfs, strict=True):
            dl = sum(tf.values())
            score = 0.0
            for term in terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                freq = tf[term]
                score += (
                    idf * freq * (self.k1 + 1) / (freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
                )
            if score > 0:
                scored.append(Hit(chunk=chunk, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]
