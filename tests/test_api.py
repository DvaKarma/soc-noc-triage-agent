from fastapi.testclient import TestClient

from triage.api import create_app
from triage.approvals import InMemoryTriageRepository
from triage.config import Settings

APPROVER = {"X-Approver-Token": "alice-token-123456"}
DISK = {"host": "srv-01", "trigger_name": "Free disk space is less than 5% on C:", "severity": "High"}


def client(make_agent, api_key="", approver_tokens="alice:alice-token-123456,bob:bob-token-1234567"):
    settings = Settings(api_key=api_key, approver_tokens=approver_tokens)
    return TestClient(create_app(settings, agent=make_agent(), repo=InMemoryTriageRepository()))


def test_health(make_agent):
    c = client(make_agent)
    assert c.get("/healthz").json() == {"status": "ok"}
    ready = c.get("/readyz").json()
    assert ready["runbooks"] == 8 and ready["approvals_enabled"] is True


def test_zabbix_webhook_and_approval_flow(make_agent):
    c = client(make_agent)
    r = c.post("/alerts/zabbix", json=DISK)
    assert r.status_code == 200
    body = r.json()
    assert body["runbook_id"] == "disk-full" and body["severity"] == "high"

    pending = c.get("/approvals").json()
    assert {"clean_temp_files", "extend_volume"} <= {p["action"] for p in pending}

    d = c.post(
        f"/approvals/{body['id']}", json={"action": "clean_temp_files", "approved": True}, headers=APPROVER
    )
    assert d.status_code == 200
    assert d.json()["approved"] is True and d.json()["by"] == "alice"

    again = c.post(
        f"/approvals/{body['id']}", json={"action": "clean_temp_files", "approved": True}, headers=APPROVER
    )
    assert again.status_code == 409

    audit = c.get("/audit").json()
    assert audit[0]["action"] == "clean_temp_files" and audit[0]["by"] == "alice"


def test_identity_comes_from_token_not_body(make_agent):
    c = client(make_agent)
    tid = c.post("/alerts/zabbix", json=DISK).json()["id"]
    d = c.post(
        f"/approvals/{tid}",
        json={"action": "extend_volume", "approved": False, "by": "ceo"},
        headers={"X-Approver-Token": "bob-token-1234567"},
    )
    assert d.json()["by"] == "bob"


def test_approval_requires_valid_token(make_agent):
    c = client(make_agent)
    tid = c.post("/alerts/zabbix", json=DISK).json()["id"]
    body = {"action": "clean_temp_files", "approved": True}
    assert c.post(f"/approvals/{tid}", json=body).status_code == 401
    assert c.post(f"/approvals/{tid}", json=body, headers={"X-Approver-Token": "nope"}).status_code == 401


def test_approvals_disabled_without_tokens(make_agent):
    c = client(make_agent, approver_tokens="")
    tid = c.post("/alerts/zabbix", json=DISK).json()["id"]
    r = c.post(f"/approvals/{tid}", json={"action": "clean_temp_files", "approved": True}, headers=APPROVER)
    assert r.status_code == 403


def test_api_key_required_when_configured(make_agent):
    c = client(make_agent, api_key="s3cret")
    payload = {"source": "generic", "host": "h", "title": "disk full"}
    assert c.post("/alerts", json=payload).status_code == 401
    assert c.post("/alerts", json=payload, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_invalid_severity_is_a_client_error(make_agent):
    c = client(make_agent)
    r = c.post("/alerts", json={"source": "generic", "host": "h", "title": "x", "severity": "bogus"})
    assert r.status_code == 422
