#!/usr/bin/env python3
"""End-to-end smoke test against a running deployment (compose, kind, or a real cluster).

python scripts/smoke.py http://localhost:8080 <API_KEY> <APPROVER_TOKEN>
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def call(base: str, method: str, path: str, body=None, headers=None) -> tuple[int, object]:
    req = urllib.request.Request(
        base + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, None


def main() -> int:
    base, api_key, approver = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
    key = {"X-API-Key": api_key}
    checks: list[tuple[str, bool]] = []

    status, ready = call(base, "GET", "/readyz")
    checks.append(("ready", status == 200 and ready["runbooks"] > 0))
    status, _ = call(base, "POST", "/alerts", {"source": "generic", "host": "h", "title": "disk full"})
    checks.append(("webhook rejects missing API key", status == 401))

    zabbix = {
        "host": "srv-files-01",
        "trigger_name": "Free disk space is less than 5% on C:",
        "severity": "High",
    }
    status, triage = call(base, "POST", "/alerts/zabbix", zabbix, key)
    checks.append(("zabbix triaged to disk-full", status == 200 and triage["runbook_id"] == "disk-full"))
    tid = triage["id"] if triage else ""

    wazuh = {
        "rule": {"id": "60204", "level": 10, "description": "Multiple Windows logon failures"},
        "agent": {"name": "srv-ad"},
        "full_log": "Event 4625 logon failure",
    }
    status, w = call(base, "POST", "/alerts/wazuh", wazuh, key)
    checks.append(("wazuh triaged to rdp-bruteforce", status == 200 and w["runbook_id"] == "rdp-bruteforce"))

    decision = {"action": "clean_temp_files", "approved": True}
    status, _ = call(base, "POST", f"/approvals/{tid}", decision, key)
    checks.append(("approval rejects missing approver token", status == 401))
    status, d = call(base, "POST", f"/approvals/{tid}", decision, {**key, "X-Approver-Token": approver})
    checks.append(("approval recorded", status == 200 and d["approved"] is True))
    status, _ = call(base, "POST", f"/approvals/{tid}", decision, {**key, "X-Approver-Token": approver})
    checks.append(("double approval is a conflict", status == 409))
    status, audit = call(base, "GET", "/audit?limit=5", headers=key)
    checks.append(("audit trail has the decision", status == 200 and audit[0]["triage_id"] == tid))

    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    failed = sum(not ok for _, ok in checks)
    print(f"{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
