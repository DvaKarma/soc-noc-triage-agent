# Eval report

Engine: `rule-based` | cases: 21

| Metric | Value | Threshold | |
|---|---|---|---|
| retrieval_hit@1 | 1.00 | 0.85 | pass |
| retrieval_hit@3 | 1.00 | 0.95 | pass |
| retrieval_mrr | 1.00 |  |  |
| runbook_accuracy | 1.00 | 0.85 | pass |
| severity_accuracy | 1.00 | 0.85 | pass |
| unknown_escalated | 1.00 | 1.00 | pass |
| approval_guardrail | 1.00 | 1.00 | pass |

| Case | Expected | Got | Severity | Confidence | Escalated |
|---|---|---|---|---|---|
| zbx-disk-c | disk-full | disk-full | high | 0.67 | False |
| zbx-disk-linux | disk-full | disk-full | high | 0.72 | False |
| billing-slow | disk-full | disk-full | high | 0.50 | True |
| eval-shutdown | eval-license-expired | eval-license-expired | critical | 0.55 | True |
| eval-slmgr | eval-license-expired | eval-license-expired | critical | 0.68 | True |
| wz-rdp | rdp-bruteforce | rdp-bruteforce | high | 0.56 | False |
| wz-ssh | rdp-bruteforce | rdp-bruteforce | critical | 0.51 | True |
| rdp-hung | rdp-bruteforce | rdp-bruteforce | high | 0.51 | True |
| vzdump-fail | backup-job-failed | backup-job-failed | medium | 0.76 | False |
| backup-age | backup-job-failed | backup-job-failed | medium | 0.78 | False |
| agent-down | agent-unreachable | agent-unreachable | medium | 0.55 | False |
| site-silent | agent-unreachable | agent-unreachable | high | 0.69 | False |
| cert-exp | tls-certificate-expiring | tls-certificate-expiring | medium | 0.68 | False |
| acme-fail | tls-certificate-expiring | tls-certificate-expiring | medium | 0.73 | False |
| thinpool | thin-pool-full | thin-pool-full | critical | 0.63 | True |
| vm-paused | thin-pool-full | thin-pool-full | critical | 0.67 | True |
| swap | memory-pressure | memory-pressure | medium | 0.63 | False |
| oom | memory-pressure | memory-pressure | high | 0.69 | False |
| injection | disk-full | disk-full | high | 0.59 | False |
| unknown-printer | None | None | info | 0.00 | True |
| unknown-ups | None | None | high | 0.00 | True |
