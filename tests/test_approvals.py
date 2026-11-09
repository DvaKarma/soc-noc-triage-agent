import json
import os

import httpx
import pytest

from triage.approvals import Approvers, InMemoryTriageRepository, TelegramNotifier
from triage.models import Alert

DSN = os.environ.get("TEST_DATABASE_URL")


def test_approvers_parsing_and_identify():
    a = Approvers("alice:alice-token-123456, bob:bob-token-1234567")
    assert a.identify("bob-token-1234567") == "bob"
    assert a.identify("wrong") is None
    with pytest.raises(ValueError):
        Approvers("alice:short")


def _result(make_agent, title="Free disk space is less than 5% on C:"):
    return make_agent().triage(Alert(source="zabbix", host="srv-01", title=title, severity="high"))


def test_telegram_sends_only_when_human_needed(make_agent):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    notifier = TelegramNotifier(
        "123:abc", "-100", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = _result(make_agent)
    assert notifier.notify(result) is True
    assert "Waiting approval" in sent[0]["text"] and sent[0]["chat_id"] == "-100"

    for a in result.proposed_actions:
        a.status = "proposed"
    result.escalate_to_human = False
    assert notifier.notify(result) is False
    assert len(sent) == 1


def test_telegram_failure_does_not_raise(make_agent):
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    notifier = TelegramNotifier("123:abc", "-100", client=httpx.Client(transport=httpx.MockTransport(boom)))
    assert notifier.notify(_result(make_agent)) is False


def _exercise(repo, make_agent):
    result = _result(make_agent)
    repo.save(result)
    assert repo.get(result.id).runbook_id == "disk-full"
    assert "clean_temp_files" in [name for r, name in repo.pending() if r.id == result.id]
    d = repo.decide(result.id, "clean_temp_files", True, "alice")
    assert d.by == "alice"
    assert repo.get(result.id).proposed_actions[1].status == "approved"
    with pytest.raises(ValueError):
        repo.decide(result.id, "clean_temp_files", True, "alice")
    with pytest.raises(KeyError):
        repo.decide("missing", "x", True, "alice")
    assert repo.audit(10)[0].action == "clean_temp_files"


def test_in_memory_repository(make_agent):
    _exercise(InMemoryTriageRepository(), make_agent)


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_postgres_repository(make_agent):
    from triage.approvals import PostgresTriageRepository

    repo = PostgresTriageRepository(DSN)
    _exercise(repo, make_agent)
    # a second instance (another replica) sees the same state
    assert PostgresTriageRepository(DSN).audit(1)[0].action == "clean_temp_files"
