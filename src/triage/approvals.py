"""Human-in-the-loop: keep triage results, track approval decisions, notify on Telegram.

Execution is intentionally out of scope: an approved action is handed to the RMM/automation
platform that already holds credentials. The agent never has write access to client systems.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

from .models import TriageResult

log = logging.getLogger(__name__)


class Decision(BaseModel):
    triage_id: str
    action: str
    approved: bool
    by: str
    at: datetime


class TriageRepository:
    """Thread-safe in-memory store. Swap for Postgres in production; the interface stays."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, TriageResult] = {}
        self.audit: list[Decision] = []

    def save(self, result: TriageResult) -> None:
        with self._lock:
            self._items[result.id] = result

    def get(self, triage_id: str) -> TriageResult | None:
        return self._items.get(triage_id)

    def pending(self) -> list[tuple[TriageResult, str]]:
        return [
            (r, a.name)
            for r in self._items.values()
            for a in r.proposed_actions
            if a.status == "pending_approval"
        ]

    def decide(self, triage_id: str, action: str, approved: bool, by: str) -> Decision:
        with self._lock:
            result = self._items.get(triage_id)
            if result is None:
                raise KeyError(triage_id)
            target = next((a for a in result.proposed_actions if a.name == action), None)
            if target is None or target.status != "pending_approval":
                raise ValueError(f"action '{action}' is not pending approval")
            target.status = "approved" if approved else "rejected"
            decision = Decision(
                triage_id=triage_id, action=action, approved=approved, by=by, at=datetime.now(UTC)
            )
            self.audit.append(decision)
            return decision


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self.enabled = bool(token and chat_id)
        self.chat_id = chat_id
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"

    @staticmethod
    def format(result: TriageResult) -> str:
        pending = [a.name for a in result.proposed_actions if a.status == "pending_approval"]
        lines = [
            f"[{result.severity.name.upper()}] {result.alert.host}: {result.alert.title}",
            f"Runbook: {result.runbook_id or 'none'} | confidence {result.confidence:.2f}",
            result.summary,
        ]
        if pending:
            lines.append("Waiting approval: " + ", ".join(pending) + f" (triage {result.id})")
        if result.escalate_to_human:
            lines.append("Escalated to on-call analyst.")
        return "\n".join(lines)

    def notify(self, result: TriageResult) -> None:
        if not self.enabled:
            return
        needs_human = result.escalate_to_human or any(
            a.status == "pending_approval" for a in result.proposed_actions
        )
        if not needs_human:
            return
        try:
            httpx.post(self.url, json={"chat_id": self.chat_id, "text": self.format(result)}, timeout=10)
        except httpx.HTTPError as exc:
            log.warning("telegram notification failed: %s", exc)
