# SOC/NOC Triage Agent

**English** · [Português](README.pt-BR.md)

[![ci](https://github.com/DvaKarma/soc-noc-triage-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/DvaKarma/soc-noc-triage-agent/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

An LLM agent that does **first-level triage of monitoring and security alerts** (Zabbix, Wazuh)
for a managed IT services team. It retrieves the right runbook with **hybrid RAG**, asks a model
for a structured decision, and then **enforces guardrails in code**. Sensitive actions always go
to a human for approval: Telegram notifies, and a named approver decides through the API.

This is a clean-room, open-source version of the pattern I run in production at
[VNC TEC](https://vnctec.com.br), where AI agents triage SOC and NOC alerts for 50+ client servers
and workstations. It contains no client data, and the runbooks are generalized from real incidents.

```
Zabbix / Wazuh webhook
        │
        ▼
 normalize ──► hybrid retrieval (BM25 + pgvector, RRF) ──► decision engine (LLM or rules)
                                                                  │
                                                                  ▼
                                     guardrails: allowlist, approval flags, severity floor,
                                     runbook must be retrieved, low evidence ⇒ escalate
                                                                  │
                         ┌────────────────────────────────────────┴───────────────┐
                         ▼                                                        ▼
               proposed actions (safe)                          pending approval ──► Telegram / API
```

## Why it is built this way

| Decision | Reason |
|---|---|
| **Guardrails in code, not in the prompt** | The model proposes and the code disposes. Actions must exist in the runbook allowlist, approval flags come from the runbook, and the model cannot lower the alert severity or pick a runbook it was not shown. These rules are covered by tests. |
| **Hybrid retrieval with Reciprocal Rank Fusion** | Alerts mix exact identifiers (`event 4625`, `vfs.fs.size[C:,pfree]`, rule ids) with free text. BM25 catches the identifiers and dense vectors catch paraphrases. RRF fuses the two rankings without calibrating their scores. |
| **"I don't know" is a valid answer** | If lexical evidence is weak, no runbook is trusted and the alert is escalated. A confident wrong answer at 3 a.m. is worse than a page. |
| **Deterministic fallback engine** | If the model times out or returns invalid JSON, a rule-based engine built from runbook metadata answers instead. Triage degrades but never goes dark. |
| **Alert text is untrusted input** | Alert payloads are wrapped as data and the system prompt tells the model to ignore instructions inside them. The eval set includes a prompt-injection case. |
| **The agent never executes** | Approved actions are handed to the RMM or automation platform that already holds credentials. The agent has no write access to client systems. |
| **Approvals are attributable** | Each approver has a personal token. The name in the audit trail comes from the token, not from the request body, and decisions lock the row in Postgres so two people cannot approve the same action twice. |
| **Provider-agnostic** | Anthropic Messages API or any OpenAI-compatible endpoint (OpenAI, Azure OpenAI, Ollama, vLLM). Embeddings work the same way, with an offline hashing embedder for CI. |

## Evals

`triage-evals` runs a labelled set of alerts (`evals/dataset.jsonl`). It covers paraphrases,
vendor-specific payloads, unknown alerts that must be escalated, and a prompt-injection attempt.
It **fails the build** when a metric drops below its threshold.

| Metric | Rule-based engine | Threshold |
|---|---|---|
| retrieval hit@1 | 1.00 | 0.85 |
| retrieval hit@3 | 1.00 | 0.95 |
| runbook accuracy (end to end) | 1.00 | 0.85 |
| severity accuracy | 1.00 | 0.85 |
| unknown alerts escalated | 1.00 | 1.00 |
| approval guardrail respected | 1.00 | 1.00 |

The dataset is small (22 cases) and synthetic: it is a regression gate, not a benchmark. One case
came from the Kubernetes smoke test: a short Wazuh alert that the first ranking formula sent to
the wrong runbook. It is now in the set so the bug cannot come back. To run
the same suite against a real model:

```bash
LLM_PROVIDER=anthropic LLM_API_KEY=... triage-evals
```

## Run it

```bash
# local, offline (no API keys)
uv venv && uv pip install -e ".[dev]"
pytest && triage-evals
uvicorn triage.api:create_app --factory --port 8080

# full stack with Postgres + pgvector
cp .env.example .env
docker compose up --build
curl -X POST localhost:8080/alerts/zabbix -H 'X-API-Key: change-me' \
     -H 'content-type: application/json' -d @examples/zabbix-disk.json
```

Interactive API docs: `http://localhost:8080/docs`.

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/alerts/zabbix` | Zabbix media-type webhook |
| POST | `/alerts/wazuh` | Wazuh custom integration |
| POST | `/alerts` | Generic, already-normalized alert |
| GET | `/triage/{id}` | Triage result with citations and guardrail notes |
| GET | `/approvals` | Actions waiting for a human |
| POST | `/approvals/{id}` | Approve or reject an action. Needs `X-Approver-Token` |
| GET | `/audit` | Who approved or rejected what, and when |
| GET | `/healthz`, `/readyz` | Probes |

Webhooks are authenticated with a shared secret in the `X-API-Key` header. Approvals also need a
personal token (`APPROVER_TOKENS="alice:token,bob:token"`); approvals are disabled when it is
empty. Tokens are compared in constant time. With `DATABASE_URL` set, triage results and the audit
trail live in Postgres and survive restarts; without it, everything stays in memory (single replica).

## Deploy

* **Container**: multi-stage `Dockerfile` that runs as a non-root user, published to GHCR by CI.
* **Kubernetes**: Helm chart in `deploy/helm/triage-agent`. It has a read-only root filesystem,
  drops all capabilities, uses an HPA, takes secrets from an existing Secret (External Secrets,
  Sealed Secrets, Infisical operator), and includes probes and an optional ingress.
* **AWS**: Terraform in `infra/terraform/aws`. It creates a VPC and a single-node k3s host with
  IMDSv2, an encrypted gp3 volume and **no SSH** (Session Manager only). HTTPS is restricted to
  the monitoring servers, and the Kubernetes API to admin CIDRs.

```bash
cd infra/terraform/aws
terraform init && terraform apply -var-file=example.tfvars
helm upgrade --install triage deploy/helm/triage-agent --set ingress.enabled=true
```

## CI

GitHub Actions runs on every push and pull request:
1. ruff lint and format, with dependencies installed from `uv.lock`
2. unit tests plus **Postgres/pgvector integration tests** against a service container
3. evals with thresholds, with the report published in the job summary
4. `pip-audit` on the locked runtime dependencies
5. `terraform fmt`/`validate`, `helm lint`/`template`
6. **end-to-end on Kubernetes**: a kind cluster with Postgres, the Helm chart with 2 replicas,
   and `scripts/smoke.py` through the Service (webhooks, auth, approvals, audit)
7. Trivy image scan (fails on fixable HIGH/CRITICAL), then push to GHCR on `main`

Actions are pinned by commit SHA and Dependabot keeps Python, Actions and Docker updated.
See [SECURITY.md](SECURITY.md) for the security model.

Run the same checks locally:

```bash
pytest && triage-evals
docker compose up -d --build && python scripts/smoke.py http://localhost:8080 change-me change-me-approver-token
./scripts/e2e-kind.sh   # needs kind, kubectl and helm
```

## Project layout

```
src/triage/
  normalize.py        Zabbix / Wazuh payloads -> Alert
  retrieval/          chunking, BM25, embeddings, vector stores (memory, pgvector), RRF fusion
  llm.py, prompts.py  decision engines (Anthropic, OpenAI-compatible, rule-based)
  agent.py            retrieve -> decide -> enforce guardrails
  approvals.py        repositories (memory, Postgres), approver tokens, audit trail, Telegram
  db.py               advisory lock so replicas do not race on schema setup
  api.py              FastAPI app
  evals.py            evaluation harness with thresholds
runbooks/             Markdown runbooks with YAML front matter (actions + approval flags)
evals/                labelled dataset and latest report
deploy/helm/          Helm chart
deploy/e2e/           test-only Postgres for the kind job
scripts/              smoke test and kind end-to-end script
infra/terraform/aws/  VPC + k3s node, SSM access
```

## Roadmap

- Telegram inline buttons for one-tap approval (today Telegram only notifies).
- Signed webhooks or mTLS instead of a shared API key.
- Correlation window: group alerts from the same site before triage (one VPN outage should not
  produce 12 tickets).
- LLM-as-judge evals for summary quality, alongside the deterministic metrics.

Author: **Vinicius Dutra**. [LinkedIn](https://www.linkedin.com/in/viniciusdutra-vnctec) ·
[Portfolio](https://viniciusdutra.netlify.app)
