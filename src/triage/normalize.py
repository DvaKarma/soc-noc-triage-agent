"""Turn vendor webhook payloads into a common Alert."""

from __future__ import annotations

from typing import Any

from .models import Alert, Severity


def from_zabbix(payload: dict[str, Any]) -> Alert:
    """Zabbix media-type webhook. Expected keys follow the usual {EVENT.*}/{HOST.*} macros."""
    tags: dict[str, str] = {}
    for tag in payload.get("tags", []) or []:
        if isinstance(tag, dict) and "tag" in tag:
            tags[str(tag["tag"])] = str(tag.get("value", ""))
    if payload.get("item_key"):
        tags["item_key"] = str(payload["item_key"])
    return Alert(
        source="zabbix",
        host=str(payload.get("host") or payload.get("hostname") or "unknown"),
        title=str(payload.get("trigger_name") or payload.get("subject") or "Zabbix event"),
        description=str(payload.get("opdata") or payload.get("message") or ""),
        severity=Severity.parse(payload.get("severity")),
        tags=tags,
    )


def _wazuh_level_to_severity(level: int) -> Severity:
    if level >= 12:
        return Severity.critical
    if level >= 10:
        return Severity.high
    if level >= 7:
        return Severity.medium
    if level >= 4:
        return Severity.low
    return Severity.info


def from_wazuh(payload: dict[str, Any]) -> Alert:
    """Wazuh integration (custom-integration JSON alert)."""
    rule = payload.get("rule", {}) or {}
    agent = payload.get("agent", {}) or {}
    data = payload.get("data", {}) or {}
    tags = {"rule_id": str(rule.get("id", ""))}
    for group in rule.get("groups", []) or []:
        tags[f"group_{group}"] = "1"
    if data.get("srcip"):
        tags["srcip"] = str(data["srcip"])
    return Alert(
        source="wazuh",
        host=str(agent.get("name") or "unknown"),
        title=str(rule.get("description") or "Wazuh alert"),
        description=str(payload.get("full_log") or ""),
        severity=_wazuh_level_to_severity(int(rule.get("level", 5))),
        tags=tags,
    )
