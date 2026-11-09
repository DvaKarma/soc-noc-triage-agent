from fastapi.testclient import TestClient

from triage.api import create_app
from triage.config import Settings


def client(make_agent, api_key=""):
    return TestClient(create_app(Settings(api_key=api_key), agent=make_agent()))


def test_health(make_agent):
    c = client(make_agent)
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/readyz").json()["runbooks"] == 8


def test_zabbix_webhook_and_approval_flow(make_agent):
    c = client(make_agent)
    r = c.post(
        "/alerts/zabbix",
        json={"host": "srv-01", "trigger_name": "Free disk space is less than 5% on C:", "severity": "High"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["runbook_id"] == "disk-full" and body["severity"] == "high"

    pending = c.get("/approvals").json()
    assert {"clean_temp_files", "extend_volume"} <= {p["action"] for p in pending}

    d = c.post(
        f"/approvals/{body['id']}", json={"action": "clean_temp_files", "approved": True, "by": "analyst"}
    )
    assert d.status_code == 200 and d.json()["approved"] is True
    again = c.post(
        f"/approvals/{body['id']}", json={"action": "clean_temp_files", "approved": True, "by": "x"}
    )
    assert again.status_code == 409


def test_api_key_required_when_configured(make_agent):
    c = client(make_agent, api_key="s3cret")
    payload = {"source": "generic", "host": "h", "title": "disk full"}
    assert c.post("/alerts", json=payload).status_code == 401
    assert c.post("/alerts", json=payload, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_invalid_severity_is_a_client_error(make_agent):
    c = client(make_agent)
    r = c.post("/alerts", json={"source": "generic", "host": "h", "title": "x", "severity": "bogus"})
    assert r.status_code == 422
