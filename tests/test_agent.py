from triage.llm import RuleBasedEngine
from triage.models import Alert, LLMDecision, ProposedAction, Severity


class FakeEngine:
    name = "fake"

    def __init__(self, decision: LLMDecision | Exception):
        self.decision = decision

    def decide(self, alert, candidates):
        if isinstance(self.decision, Exception):
            raise self.decision
        return self.decision


DISK = Alert(source="zabbix", host="srv-01", title="Free disk space is less than 5% on C:", severity="high")


def test_rule_based_end_to_end(make_agent):
    result = make_agent().triage(DISK)
    assert result.runbook_id == "disk-full"
    statuses = {a.name: a.status for a in result.proposed_actions}
    assert statuses["collect_disk_usage"] == "proposed"
    assert statuses["clean_temp_files"] == "pending_approval"
    assert result.citations and result.citations[0].runbook_id == "disk-full"


def test_model_cannot_skip_approval_or_invent_actions(make_agent):
    decision = LLMDecision(
        runbook_id="disk-full",
        severity="high",
        summary="s",
        confidence=0.9,
        proposed_actions=[
            ProposedAction(name="clean_temp_files", requires_approval=False, status="approved"),
            ProposedAction(name="format_disk"),
        ],
    )
    result = make_agent(engine=FakeEngine(decision)).triage(DISK)
    assert [(a.name, a.status) for a in result.proposed_actions] == [("clean_temp_files", "pending_approval")]
    assert any("format_disk" in n for n in result.guardrail_notes)


def test_model_cannot_lower_severity(make_agent):
    decision = LLMDecision(runbook_id="disk-full", severity="low", summary="s", confidence=0.9)
    result = make_agent(engine=FakeEngine(decision)).triage(DISK)
    assert result.severity == Severity.high


def test_runbook_outside_retrieved_set_is_discarded(make_agent):
    decision = LLMDecision(runbook_id="thin-pool-full", severity="high", summary="s", confidence=0.9)
    result = make_agent(engine=FakeEngine(decision)).triage(DISK)
    assert result.runbook_id is None
    assert result.escalate_to_human


def test_engine_failure_falls_back_to_rules(make_agent):
    result = make_agent(engine=FakeEngine(TimeoutError("model timeout"))).triage(DISK)
    assert result.runbook_id == "disk-full"
    assert result.engine == "rule-based (fallback)"


def test_unknown_alert_is_escalated(make_agent):
    alert = Alert(source="generic", host="prn-01", title="Printer toner level low", severity="info")
    result = make_agent(engine=RuleBasedEngine()).triage(alert)
    assert result.runbook_id is None and result.escalate_to_human
    assert result.severity == Severity.info


def test_invalid_model_severity_keeps_alert_severity(make_agent):
    decision = LLMDecision(runbook_id="disk-full", severity="extreme", summary="s", confidence=0.9)
    result = make_agent(engine=FakeEngine(decision)).triage(DISK)
    assert result.severity == Severity.high
    assert any("invalid severity" in n for n in result.guardrail_notes)


def test_triage_result_json_roundtrip(make_agent):
    result = make_agent().triage(DISK)
    again = type(result).model_validate_json(result.model_dump_json())
    assert again == result
