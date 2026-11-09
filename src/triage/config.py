"""Configuration from environment variables (12-factor)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from .agent import TriageAgent
from .approvals import InMemoryTriageRepository, PostgresTriageRepository, TriageRepository
from .llm import AnthropicBackend, ChatEngine, DecisionEngine, OpenAICompatibleBackend, RuleBasedEngine
from .retrieval import HybridRetriever, load_runbooks
from .retrieval.embeddings import Embedder, HashingEmbedder, OpenAICompatibleEmbedder
from .retrieval.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore


class Settings(BaseModel):
    runbooks_dir: Path = Path("runbooks")
    llm_provider: str = "rule-based"  # rule-based | anthropic | openai
    llm_model: str = "claude-sonnet-5-5"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    embeddings_provider: str = "hashing"  # hashing | openai
    embeddings_model: str = "text-embedding-3-small"
    embeddings_dim: int = 384
    database_url: str = ""
    api_key: str = ""
    approver_tokens: str = ""  # "alice:long-random-token,bob:another-token"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    min_confidence: float = 0.55

    @classmethod
    def from_env(cls) -> Settings:
        fields = {name: os.environ[name.upper()] for name in cls.model_fields if name.upper() in os.environ}
        return cls(**fields)


def build_embedder(s: Settings) -> Embedder:
    if s.embeddings_provider == "openai":
        return OpenAICompatibleEmbedder(s.llm_base_url, s.llm_api_key, s.embeddings_model, s.embeddings_dim)
    return HashingEmbedder(s.embeddings_dim)


def build_engine(s: Settings) -> DecisionEngine:
    if s.llm_provider == "anthropic":
        return ChatEngine(AnthropicBackend(s.llm_api_key, s.llm_model), f"anthropic:{s.llm_model}")
    if s.llm_provider == "openai":
        return ChatEngine(
            OpenAICompatibleBackend(s.llm_base_url, s.llm_api_key, s.llm_model), f"openai:{s.llm_model}"
        )
    return RuleBasedEngine()


def build_agent(s: Settings) -> TriageAgent:
    embedder = build_embedder(s)
    store: VectorStore = (
        PgVectorStore(s.database_url, embedder) if s.database_url else InMemoryVectorStore(embedder)
    )
    return TriageAgent.build(
        load_runbooks(s.runbooks_dir),
        HybridRetriever(store),
        engine=build_engine(s),
        min_confidence=s.min_confidence,
    )


def build_repository(s: Settings) -> TriageRepository:
    return PostgresTriageRepository(s.database_url) if s.database_url else InMemoryTriageRepository()
