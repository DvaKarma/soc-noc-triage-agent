import json

from triage.llm import ChatEngine, extract_json
from triage.models import Alert


def test_extract_json_from_fenced_reply():
    assert extract_json('Sure:\n```json\n{"summary": "x"}\n```') == {"summary": "x"}


def test_chat_engine_parses_backend_reply(runbooks):
    class Backend:
        def complete(self, system, user):
            assert "untrusted" in system and "<alert>" in user
            return json.dumps(
                {"runbook_id": "disk-full", "severity": "high", "summary": "disk", "confidence": 0.8}
            )

    book = runbooks["disk-full"]
    decision = ChatEngine(Backend(), "test").decide(
        Alert(source="generic", host="h", title="disk"), [(book, 1.0, [])]
    )
    assert decision.runbook_id == "disk-full"
