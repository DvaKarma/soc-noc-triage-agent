"""Embedding providers.

`HashingEmbedder` is deterministic and offline (feature hashing of words and character
trigrams), so tests, CI and evals run without network or API keys. `OpenAICompatibleEmbedder`
talks to any `/v1/embeddings` endpoint (OpenAI, Azure OpenAI, Ollama, vLLM, LiteLLM...).
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from .text import tokenize


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashingEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        words = tokenize(text)
        grams = [w[i : i + 3] for w in words for i in range(max(len(w) - 2, 1))]
        return words + [f"#{g}" for g in grams]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for feat in self._features(text):
                digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                vec[idx] += sign * (1.0 if not feat.startswith("#") else 0.5)
            out.append(_normalize(vec))
        return out


class OpenAICompatibleEmbedder:
    def __init__(self, base_url: str, api_key: str, model: str, dim: int, timeout: float = 30) -> None:
        self.dim = dim
        self.model = model
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.post("/embeddings", json={"model": self.model, "input": texts})
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [_normalize(d["embedding"]) for d in data]
