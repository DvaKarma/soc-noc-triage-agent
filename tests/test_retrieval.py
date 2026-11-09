from triage.retrieval import HybridRetriever, chunk_runbook
from triage.retrieval.bm25 import BM25Index
from triage.retrieval.embeddings import HashingEmbedder
from triage.retrieval.vector_store import InMemoryVectorStore


def test_chunks_have_overview_and_sections(runbooks):
    chunks = chunk_runbook(runbooks["disk-full"])
    assert chunks[0].heading == "Overview"
    assert {"Symptoms", "Diagnosis", "Remediation", "Escalation"} <= {c.heading for c in chunks}


def test_hashing_embedder_is_deterministic_and_normalized():
    emb = HashingEmbedder(64)
    a, b = emb.embed(["disk full on C:", "disk full on C:"])
    assert a == b
    assert abs(sum(x * x for x in a) - 1) < 1e-9


def test_bm25_prefers_exact_identifiers(runbooks):
    index = BM25Index()
    for book in runbooks.values():
        index.add(chunk_runbook(book))
    assert index.search("event 4625 logon failure", k=1)[0].chunk.runbook_id == "rdp-bruteforce"


def test_hybrid_ranks_paraphrase(runbooks):
    retriever = HybridRetriever(InMemoryVectorStore(HashingEmbedder()))
    for book in runbooks.values():
        retriever.add(chunk_runbook(book))
    ranked = retriever.rank_runbooks("virtual machines froze, datastore out of space", k=3)
    assert ranked[0][0] == "thin-pool-full"
