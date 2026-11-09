"""Human-in-the-loop: store triage results, record approval decisions, notify on Telegram.

Execution is intentionally out of scope: an approved action is handed to the RMM/automation
platform that already holds credentials. The agent never has write access to client systems.
"""

from __future__ import annotations

import hmac
import logging
import threading
from datetime import UTC, datetime
from typing import Protocol

import httpx
from pydantic import BaseModel

from .db import schema_lock
from .models import TriageResult

log = logging.getLogger(__name__)


class Decision(BaseModel):
    triage_id: str
    action: str
    approved: bool
    by: str
    at: datetime


class TriageRepository(Protocol):
    def save(self, result: TriageResult) -> None: ...

    def get(self, triage_id: str) -> TriageResult | None: ...

    def pending(self) -> list[tuple[TriageResult, str]]: ...

    def decide(self, triage_id: str, action: str, approved: bool, by: str) -> Decision: ...

    def audit(self, limit: int = 100) -> list[Decision]: ...


def _apply_decision(result: TriageResult, action: str, approved: bool) -> None:
    target = next((a for a in result.proposed_actions if a.name == action), None)
    if target is None or target.status != "pending_approval":
        raise ValueError(f"action '{action}' is not pending approval")
    target.status = "approved" if approved else "rejected"


def _pending(results: list[TriageResult]) -> list[tuple[TriageResult, str]]:
    return [(r, a.name) for r in results for a in r.proposed_actions if a.status == "pending_approval"]


class InMemoryTriageRepository:
    """For tests and single-replica demos. Data is lost on restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, TriageResult] = {}
        self._audit: list[Decision] = []

    def save(self, result: TriageResult) -> None:
        with self._lock:
            self._items[result.id] = result

    def get(self, triage_id: str) -> TriageResult | None:
        return self._items.get(triage_id)

    def pending(self) -> list[tuple[TriageResult, str]]:
        return _pending(list(self._items.values()))

    def decide(self, triage_id: str, action: str, approved: bool, by: str) -> Decision:
        with self._lock:
            result = self._items.get(triage_id)
            if result is None:
                raise KeyError(triage_id)
            _apply_decision(result, action, approved)
            decision = Decision(
                triage_id=triage_id, action=action, approved=approved, by=by, at=datetime.now(UTC)
            )
            self._audit.append(decision)
            return decision

    def audit(self, limit: int = 100) -> list[Decision]:
        return list(reversed(self._audit))[:limit]


class PostgresTriageRepository:
    """Durable store shared by all replicas. Decisions lock the row (SELECT ... FOR UPDATE)."""

    def __init__(self, dsn: str) -> None:
        import psycopg  # optional dependency: pip install .[postgres]

        self._psycopg = psycopg
        self.dsn = dsn
        with psycopg.connect(dsn, autocommit=True) as conn, schema_lock(conn):
            conn.execute(
                """CREATE TABLE IF NOT EXISTS triage_results (
                    id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(),
                    result jsonb NOT NULL)"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS approval_decisions (
                    id bigserial PRIMARY KEY, triage_id text NOT NULL REFERENCES triage_results(id),
                    action text NOT NULL, approved boolean NOT NULL, decided_by text NOT NULL,
                    decided_at timestamptz NOT NULL)"""
            )

    def _conn(self):
        return self._psycopg.connect(self.dsn)

    def save(self, result: TriageResult) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO triage_results (id, result) VALUES (%s, %s::jsonb)
                   ON CONFLICT (id) DO UPDATE SET result = EXCLUDED.result""",
                (result.id, result.model_dump_json()),
            )

    def get(self, triage_id: str) -> TriageResult | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT result::text FROM triage_results WHERE id = %s", (triage_id,)
            ).fetchone()
        return TriageResult.model_validate_json(row[0]) if row else None

    def pending(self) -> list[tuple[TriageResult, str]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT result::text FROM triage_results
                   WHERE result->'proposed_actions' @> '[{"status": "pending_approval"}]'
                   ORDER BY created_at"""
            ).fetchall()
        return _pending([TriageResult.model_validate_json(r[0]) for r in rows])

    def decide(self, triage_id: str, action: str, approved: bool, by: str) -> Decision:
        with self._conn() as conn, conn.transaction():
            row = conn.execute(
                "SELECT result::text FROM triage_results WHERE id = %s FOR UPDATE", (triage_id,)
            ).fetchone()
            if row is None:
                raise KeyError(triage_id)
            result = TriageResult.model_validate_json(row[0])
            _apply_decision(result, action, approved)
            decision = Decision(
                triage_id=triage_id, action=action, approved=approved, by=by, at=datetime.now(UTC)
            )
            conn.execute(
                "UPDATE triage_results SET result = %s::jsonb WHERE id = %s",
                (result.model_dump_json(), triage_id),
            )
            conn.execute(
                """INSERT INTO approval_decisions (triage_id, action, approved, decided_by, decided_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (triage_id, action, approved, by, decision.at),
            )
        return decision

    def audit(self, limit: int = 100) -> list[Decision]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT triage_id, action, approved, decided_by, decided_at FROM approval_decisions
                   ORDER BY id DESC LIMIT %s""",
                (limit,),
            ).fetchall()
        return [Decision(triage_id=r[0], action=r[1], approved=r[2], by=r[3], at=r[4]) for r in rows]


class Approvers:
    """Each approver has a personal token (APPROVER_TOKENS="alice:tok1,bob:tok2").

    The identity recorded in the audit trail comes from the token, never from the request body.
    """

    def __init__(self, spec: str) -> None:
        self._tokens: list[tuple[str, str]] = []
        for item in filter(None, (p.strip() for p in spec.split(","))):
            name, sep, token = item.partition(":")
            if not sep or not name or len(token) < 12:
                raise ValueError("APPROVER_TOKENS entries must be name:token with a token of 12+ chars")
            self._tokens.append((name, token))

    @property
    def configured(self) -> bool:
        return bool(self._tokens)

    def identify(self, token: str) -> str | None:
        match = None
        for name, expected in self._tokens:  # check all entries: no early exit timing signal
            if hmac.compare_digest(token.encode(), expected.encode()):
                match = name
        return match


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None) -> None:
        self.enabled = bool(token and chat_id)
        self.chat_id = chat_id
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.client = client or httpx.Client(timeout=10)

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

    def notify(self, result: TriageResult) -> bool:
        """Send only when a human is needed. Returns True when a message was sent."""
        if not self.enabled:
            return False
        needs_human = result.escalate_to_human or any(
            a.status == "pending_approval" for a in result.proposed_actions
        )
        if not needs_human:
            return False
        try:
            resp = self.client.post(self.url, json={"chat_id": self.chat_id, "text": self.format(result)})
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:  # never fail the triage because the chat is down
            log.warning("telegram notification failed: %s", exc)
            return False
