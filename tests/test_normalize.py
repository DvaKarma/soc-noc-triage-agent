from triage.models import Severity
from triage.normalize import from_wazuh, from_zabbix


def test_zabbix_payload():
    alert = from_zabbix(
        {
            "host": "srv-01",
            "trigger_name": "Free disk space is less than 5% on C:",
            "severity": "Disaster",
            "opdata": "3% free",
            "item_key": "vfs.fs.size[C:,pfree]",
            "tags": [{"tag": "scope", "value": "capacity"}],
        }
    )
    assert alert.source == "zabbix"
    assert alert.severity == Severity.critical
    assert alert.tags == {"scope": "capacity", "item_key": "vfs.fs.size[C:,pfree]"}


def test_wazuh_level_mapping():
    alert = from_wazuh(
        {
            "rule": {
                "id": "60204",
                "level": 10,
                "description": "Multiple Windows logon failures",
                "groups": ["win"],
            },
            "agent": {"name": "srv-ad"},
            "data": {"srcip": "10.0.0.9"},
            "full_log": "event 4625",
        }
    )
    assert alert.severity == Severity.high
    assert alert.tags["rule_id"] == "60204"
    assert alert.tags["srcip"] == "10.0.0.9"


def test_severity_aliases():
    assert Severity.parse("average") == Severity.medium
    assert Severity.parse("warning") == Severity.low
    assert Severity.parse(9) == Severity.critical
