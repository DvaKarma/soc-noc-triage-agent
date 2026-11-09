"""Decision engines.

* `RuleBasedEngine`: deterministic baseline built only from runbook metadata. Used offline,
  in CI and as the fallback when the model call fails, so the pipeline never goes dark.
* `ChatEngine`: calls an LLM (Anthropic Messages API or any OpenAI-compatible chat endpoint)
  and asks for a strict JSON decision grounded in the retrieved runbook excerpts.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from .models import Alert, Hit, LLMDecision, ProposedAction, Runbook
from .prompts import SYSTEM_PROMPT, build_user_prompt

Candidate = tuple[Runbook, float, list[Hit]]


class DecisionEngine(Protocol):
    name: str

    def decide(self, alert: Alert, candidates: list[Candidate]) -> LLMDecision: ...


class RuleBasedEngine:
    name = "rule-based"

    def decide(self, alert: Alert, candidates: list[Candidate]) -> LLMDecision:
        if not candidates:
            return LLMDecision(
                summary=f"No runbook matched '{alert.title}'.", severity=alert.severity.name, confidence=0.0
            )
        book, top, _ = candidates[0]
        runner_up = candidates[1][1] if len(candidates) > 1 else 0.0
        margin = (top - runner_up) / top if top else 0.0
        severity = max(alert.severity, book.default_severity)
        actions = [
            ProposedAction(name=a.name, reason=a.description, requires_approval=a.requires_approval)
            for a in book.actions
        ]
        return LLMDecision(
            runbook_id=book.id,
            severity=severity.name,
            summary=f"{alert.title} on {alert.host}: matches runbook '{book.title}'.",
            hypothesis=f"Pattern consistent with '{book.title}'. Follow the diagnosis section before acting.",
            proposed_actions=actions,
            confidence=round(min(0.95, 0.45 + 0.5 * margin), 2),
        )


class ChatBackend(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicBackend:
    def __init__(self, api_key: str, model: str, timeout: float = 60) -> None:
        self.model = model
        self.client = httpx.Client(
            base_url="https://api.anthropic.com/v1",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=timeout,
        )

    def complete(self, system: str, user: str) -> str:
        resp = self.client.post(
            "/messages",
            json={
                "model": self.model,
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        return "".join(b.get("text", "") for b in resp.json()["content"] if b.get("type") == "text")


class OpenAICompatibleBackend:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60) -> None:
        self.model = model
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )

    def complete(self, system: str, user: str) -> str:
        resp = self.client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences; take the outermost object."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


class ChatEngine:
    def __init__(self, backend: ChatBackend, label: str) -> None:
        self.backend = backend
        self.name = label

    def decide(self, alert: Alert, candidates: list[Candidate]) -> LLMDecision:
        reply = self.backend.complete(SYSTEM_PROMPT, build_user_prompt(alert, candidates))
        return LLMDecision.model_validate(extract_json(reply))
