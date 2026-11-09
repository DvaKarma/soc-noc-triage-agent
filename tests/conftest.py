from pathlib import Path

import pytest

from triage.agent import TriageAgent
from triage.retrieval import HybridRetriever, load_runbooks
from triage.retrieval.embeddings import HashingEmbedder
from triage.retrieval.vector_store import InMemoryVectorStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def runbooks():
    return load_runbooks(ROOT / "runbooks")


@pytest.fixture
def make_agent(runbooks):
    def _make(**kw) -> TriageAgent:
        return TriageAgent.build(runbooks, HybridRetriever(InMemoryVectorStore(HashingEmbedder())), **kw)

    return _make
