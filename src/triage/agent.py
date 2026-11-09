"""Triage pipeline: retrieve -> decide -> enforce guardrails.

The model proposes; this module decides what is allowed. Guardrails are code, not prompt:
the runbook allowlist and approval flags always win over the model output.
"""

from __future__ import annotations

import logging

from .llm import Candidate, DecisionEngine, RuleBasedEngine
from .models import Alert, Citation, LLMDecision, ProposedAction, Runbook, Severity, TriageResult
from .retrieval import HybridRetriever, chunk_runbook

log = logging.getLogger(__name__)


class TriageAgent:
    def __init__(
        self,
        runbooks: dict[str, Runbook],
        retriever: HybridRetriever,
        engine: DecisionEngine | None = None,
        min_confidence: float = 0.55,
        min_lexical_score: float = 3.0,
        top_k: int = 3,
    ) -> None:
        self.runbooks = runbooks
        self.retriever = retriever
        self.engine = engine or RuleBasedEngine()
        self.fallback = RuleBasedEngine()
        self.min_confidence = min_confidence
        self.min_lexical_score = min_lexical_score
        self.top_k = top_k

    @classmethod
    def build(cls, runbooks: dict[str, Runbook], retriever: HybridRetriever, **kw) -> TriageAgent:
        for book in runbooks.values():
            retriever.add(chunk_runbook(book))
        return cls(runbooks, retriever, **kw)

    def candidates(self, alert: Alert) -> list[Candidate]:
        ranked = self.retriever.rank_runbooks(alert.query_text(), k=self.top_k)
        return [(self.runbooks[rb], score, hits) for rb, score, hits in ranked if rb in self.runbooks]

    def lexical_support(self, alert: Alert) -> float:
        hits = self.retriever.bm25.search(alert.query_text(), k=1)
        return hits[0].score if hits else 0.0

    def triage(self, alert: Alert) -> TriageResult:
        notes: list[str] = []
        candidates = self.candidates(alert)
        support = self.lexical_support(alert)
        if support < self.min_lexical_score:
            notes.append(f"weak lexical evidence ({support:.2f}); runbook match is not trusted")
            candidates = []

        engine_name = self.engine.name
        try:
            decision = self.engine.decide(alert, candidates)
        except Exception as exc:  # model down, timeout, invalid JSON: degrade, never go dark
            log.warning("engine %s failed: %s; using rule-based fallback", self.engine.name, exc)
            notes.append(
                f"engine '{self.engine.name}' failed ({type(exc).__name__}); used rule-based fallback"
            )
            decision = self.fallback.decide(alert, candidates)
            engine_name = f"{self.fallback.name} (fallback)"

        return self._enforce(alert, decision, candidates, notes, engine_name)

    def _enforce(
        self, alert: Alert, d: LLMDecision, candidates: list[Candidate], notes: list[str], engine: str
    ) -> TriageResult:
        allowed_ids = {book.id for book, _, _ in candidates}
        book = self.runbooks.get(d.runbook_id) if d.runbook_id in allowed_ids else None
        if d.runbook_id and book is None:
            notes.append(f"model chose runbook '{d.runbook_id}' outside the retrieved set; discarded")

        try:
            severity = Severity.parse(d.severity)
        except ValueError:
            severity = alert.severity
            notes.append(f"invalid severity '{d.severity}' from model; kept alert severity")
        if severity < alert.severity:
            notes.append(f"model tried to lower severity to {severity.name}; kept {alert.severity.name}")
            severity = alert.severity

        actions: list[ProposedAction] = []
        for proposed in d.proposed_actions:
            spec = book.action(proposed.name) if book else None
            if spec is None:
                notes.append(f"action '{proposed.name}' is not in the runbook allowlist; dropped")
                continue
            actions.append(
                ProposedAction(
                    name=spec.name,
                    reason=proposed.reason or spec.description,
                    requires_approval=spec.requires_approval,  # runbook decides, never the model
                    status="pending_approval" if spec.requires_approval else "proposed",
                )
            )

        confidence = d.confidence if book else min(d.confidence, 0.2)
        escalate = book is None or confidence < self.min_confidence or severity >= Severity.critical
        citations = [
            Citation(runbook_id=b.id, heading=h.chunk.heading, score=round(h.score, 4))
            for b, _, hits in candidates
            for h in hits[:2]
            if book and b.id == book.id
        ]
        return TriageResult(
            alert=alert,
            runbook_id=book.id if book else None,
            severity=severity,
            summary=d.summary,
            hypothesis=d.hypothesis,
            proposed_actions=actions,
            confidence=round(confidence, 2),
            escalate_to_human=escalate,
            citations=citations,
            engine=engine,
            guardrail_notes=notes,
        )
