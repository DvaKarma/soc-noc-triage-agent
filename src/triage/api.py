"""HTTP API: webhooks for Zabbix/Wazuh, triage lookup and approval decisions."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from . import __version__
from .agent import TriageAgent
from .approvals import Approvers, Decision, TelegramNotifier, TriageRepository
from .config import Settings, build_agent, build_repository
from .models import Alert, TriageResult
from .normalize import from_wazuh, from_zabbix


class DecisionIn(BaseModel):
    action: str
    approved: bool


def create_app(
    settings: Settings | None = None,
    agent: TriageAgent | None = None,
    repo: TriageRepository | None = None,
    notifier: TelegramNotifier | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    agent = agent or build_agent(settings)
    repo = repo or build_repository(settings)
    notifier = notifier or TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    approvers = Approvers(settings.approver_tokens)
    app = FastAPI(title="SOC/NOC Triage Agent", version=__version__)

    def auth(x_api_key: str = Header(default="")) -> None:
        if settings.api_key and not hmac.compare_digest(x_api_key.encode(), settings.api_key.encode()):
            raise HTTPException(status_code=401, detail="invalid API key")

    def approver(x_approver_token: str = Header(default="")) -> str:
        if not approvers.configured:
            raise HTTPException(status_code=403, detail="approvals disabled: APPROVER_TOKENS is not set")
        name = approvers.identify(x_approver_token)
        if name is None:
            raise HTTPException(status_code=401, detail="invalid approver token")
        return name

    def run(alert: Alert) -> TriageResult:
        result = agent.triage(alert)
        repo.save(result)
        notifier.notify(result)
        return result

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        return {
            "status": "ready",
            "runbooks": len(agent.runbooks),
            "engine": agent.engine.name,
            "storage": type(repo).__name__,
            "approvals_enabled": approvers.configured,
        }

    @app.post("/alerts/zabbix", response_model=TriageResult, dependencies=[Depends(auth)])
    def zabbix(payload: dict[str, Any]) -> TriageResult:
        return run(from_zabbix(payload))

    @app.post("/alerts/wazuh", response_model=TriageResult, dependencies=[Depends(auth)])
    def wazuh(payload: dict[str, Any]) -> TriageResult:
        return run(from_wazuh(payload))

    @app.post("/alerts", response_model=TriageResult, dependencies=[Depends(auth)])
    def generic(alert: Alert) -> TriageResult:
        return run(alert)

    @app.get("/triage/{triage_id}", response_model=TriageResult, dependencies=[Depends(auth)])
    def get_triage(triage_id: str) -> TriageResult:
        result = repo.get(triage_id)
        if result is None:
            raise HTTPException(status_code=404, detail="not found")
        return result

    @app.get("/approvals", dependencies=[Depends(auth)])
    def approvals() -> list[dict[str, Any]]:
        return [
            {
                "triage_id": r.id,
                "action": name,
                "host": r.alert.host,
                "title": r.alert.title,
                "severity": r.severity.name,
            }
            for r, name in repo.pending()
        ]

    @app.post("/approvals/{triage_id}", response_model=Decision, dependencies=[Depends(auth)])
    def decide(triage_id: str, body: DecisionIn, who: str = Depends(approver)) -> Decision:
        try:
            return repo.decide(triage_id, body.action, body.approved, who)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="triage not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/audit", response_model=list[Decision], dependencies=[Depends(auth)])
    def audit(limit: int = Query(default=100, ge=1, le=1000)) -> list[Decision]:
        return repo.audit(limit)

    return app
