from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator


class Severity(IntEnum):
    info = 1
    low = 2
    medium = 3
    high = 4
    critical = 5

    @classmethod
    def parse(cls, value: str | int | Severity | None) -> Severity:
        if value is None:
            return cls.medium
        if isinstance(value, Severity):
            return value
        if isinstance(value, int):
            return cls(max(1, min(5, value)))
        aliases = {
            "information": "info",
            "not classified": "info",
            "warning": "low",
            "average": "medium",
            "disaster": "critical",
        }
        key = aliases.get(value.strip().lower(), value.strip().lower())
        if key not in cls.__members__:
            raise ValueError(f"unknown severity: {value!r}")
        return cls[key]


class Alert(BaseModel):
    """Source-agnostic alert, produced by the normalizers."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    source: Literal["zabbix", "wazuh", "generic"]
    host: str
    title: str
    description: str = ""
    severity: Severity = Severity.medium
    tags: dict[str, str] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v: object) -> Severity:
        return Severity.parse(v)  # type: ignore[arg-type]

    @field_serializer("severity")
    def _sev_out(self, v: Severity) -> str:
        return v.name

    def query_text(self) -> str:
        tags = " ".join(f"{k} {v}" for k, v in self.tags.items())
        return f"{self.title}. {self.description} {tags}".strip()


class Action(BaseModel):
    name: str
    description: str
    requires_approval: bool = True


class Runbook(BaseModel):
    id: str
    title: str
    sources: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    default_severity: Severity = Severity.medium
    actions: list[Action] = Field(default_factory=list)
    body: str = ""

    @field_validator("default_severity", mode="before")
    @classmethod
    def _sev(cls, v: object) -> Severity:
        return Severity.parse(v)  # type: ignore[arg-type]

    def action(self, name: str) -> Action | None:
        return next((a for a in self.actions if a.name == name), None)


class Chunk(BaseModel):
    id: str
    runbook_id: str
    heading: str
    text: str


class Hit(BaseModel):
    chunk: Chunk
    score: float


class ProposedAction(BaseModel):
    name: str
    reason: str = ""
    requires_approval: bool = True
    status: Literal["proposed", "pending_approval", "approved", "rejected"] = "proposed"


class LLMDecision(BaseModel):
    """Raw structured output expected from the model (validated, never trusted blindly)."""

    runbook_id: str | None = None
    severity: str = "medium"
    summary: str
    hypothesis: str = ""
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Citation(BaseModel):
    runbook_id: str
    heading: str
    score: float


class TriageResult(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    alert: Alert
    runbook_id: str | None
    severity: Severity
    summary: str
    hypothesis: str
    proposed_actions: list[ProposedAction]
    confidence: float
    escalate_to_human: bool
    citations: list[Citation]
    engine: str
    guardrail_notes: list[str] = Field(default_factory=list)

    @field_serializer("severity")
    def _sev_out(self, v: Severity) -> str:
        return v.name
