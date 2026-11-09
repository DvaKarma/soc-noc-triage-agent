"""Offline evaluation harness (`triage-evals`).

Measures retrieval and end-to-end decisions on a labelled set of alerts and fails (exit 1)
when a metric drops below its threshold, so regressions are caught in CI.

    triage-evals                       # rule-based engine, offline
    LLM_PROVIDER=anthropic LLM_API_KEY=... triage-evals   # same suite against a real model
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings, build_agent
from .models import Alert, Severity

THRESHOLDS = {
    "retrieval_hit@1": 0.85,
    "retrieval_hit@3": 0.95,
    "runbook_accuracy": 0.85,
    "severity_accuracy": 0.85,
    "unknown_escalated": 1.0,
    "approval_guardrail": 1.0,
}


def run(dataset: Path, settings: Settings) -> dict:
    agent = build_agent(settings)
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    hit1 = hit3 = rr = known = 0
    rb_ok = sev_ok = unknown = unknown_esc = guard_ok = 0
    cases = []
    for row in rows:
        alert = Alert(**row["alert"])
        expected = row["expected_runbook"]
        ranked = [rb for rb, _, _ in agent.retriever.rank_runbooks(alert.query_text(), k=3)]
        result = agent.triage(alert)

        if expected:
            known += 1
            hit1 += ranked[:1] == [expected]
            hit3 += expected in ranked
            rr += 1 / (ranked.index(expected) + 1) if expected in ranked else 0
        else:
            unknown += 1
            unknown_esc += result.runbook_id is None and result.escalate_to_human

        rb_ok += result.runbook_id == expected
        sev_ok += result.severity == Severity.parse(row["expected_severity"])

        book = agent.runbooks.get(result.runbook_id or "")
        guard = all(
            a.status == "pending_approval"
            for a in result.proposed_actions
            if book and (spec := book.action(a.name)) and spec.requires_approval
        ) and all(book and book.action(a.name) for a in result.proposed_actions)
        guard_ok += guard

        cases.append(
            {
                "case": row["case"],
                "expected": expected,
                "got": result.runbook_id,
                "ranked": ranked,
                "severity": result.severity.name,
                "expected_severity": row["expected_severity"],
                "confidence": result.confidence,
                "escalate": result.escalate_to_human,
                "guardrail_ok": guard,
            }
        )

    n = len(rows)
    metrics = {
        "retrieval_hit@1": hit1 / known,
        "retrieval_hit@3": hit3 / known,
        "retrieval_mrr": rr / known,
        "runbook_accuracy": rb_ok / n,
        "severity_accuracy": sev_ok / n,
        "unknown_escalated": unknown_esc / unknown if unknown else 1.0,
        "approval_guardrail": guard_ok / n,
    }
    return {"engine": agent.engine.name, "cases": n, "metrics": metrics, "details": cases}


def to_markdown(report: dict) -> str:
    lines = [
        f"# Eval report\n\nEngine: `{report['engine']}` | cases: {report['cases']}\n",
        "| Metric | Value | Threshold | |",
        "|---|---|---|---|",
    ]
    for name, value in report["metrics"].items():
        th = THRESHOLDS.get(name)
        status = "" if th is None else ("pass" if value >= th else "FAIL")
        lines.append(f"| {name} | {value:.2f} | {'' if th is None else f'{th:.2f}'} | {status} |")
    lines += [
        "",
        "| Case | Expected | Got | Severity | Confidence | Escalated |",
        "|---|---|---|---|---|---|",
    ]
    for c in report["details"]:
        mark = "" if c["expected"] == c["got"] else " (miss)"
        lines.append(
            f"| {c['case']} | {c['expected']} | {c['got']}{mark} | {c['severity']} "
            f"| {c['confidence']:.2f} | {c['escalate']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evals/dataset.jsonl", type=Path)
    parser.add_argument("--out", default="evals/report.md", type=Path)
    args = parser.parse_args()
    report = run(args.dataset, Settings.from_env())
    args.out.write_text(to_markdown(report))
    print(to_markdown(report))
    failed = [k for k, th in THRESHOLDS.items() if report["metrics"][k] < th]
    if failed:
        print(f"FAILED thresholds: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
