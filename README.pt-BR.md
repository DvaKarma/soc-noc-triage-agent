# SOC/NOC Triage Agent

[English](README.md) · **Português**

[![ci](https://github.com/DvaKarma/soc-noc-triage-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/DvaKarma/soc-noc-triage-agent/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Agente de IA que faz a **primeira triagem de alertas de monitoramento e segurança** (Zabbix e
Wazuh) para uma equipe de TI gerenciada. Ele encontra o runbook certo com **RAG híbrido**, pede
ao modelo uma decisão estruturada e depois **aplica as travas de segurança em código**. Ação
sensível sempre vai para aprovação humana: o Telegram avisa e um aprovador identificado decide pela API.

É uma versão aberta, escrita do zero, do padrão que opero em produção na
[VNC TEC](https://vnctec.com.br), onde agentes de IA fazem a triagem dos alertas de SOC e NOC de
mais de 50 servidores e estações de clientes. Não há nenhum dado de cliente aqui: os runbooks são
generalizações de incidentes reais.

```
Webhook do Zabbix / Wazuh
        │
        ▼
 normalização ──► busca híbrida (BM25 + pgvector, RRF) ──► motor de decisão (LLM ou regras)
                                                                  │
                                                                  ▼
                       travas: lista de ações permitidas, aprovação definida pelo runbook,
                       severidade mínima, runbook precisa ter sido recuperado, evidência fraca ⇒ escala
                                                                  │
                         ┌────────────────────────────────────────┴───────────────┐
                         ▼                                                        ▼
               ações propostas (seguras)                    aguardando aprovação ──► Telegram / API
```

## Por que foi construído assim

| Decisão | Motivo |
|---|---|
| **Travas em código, não no prompt** | O modelo propõe e o código decide o que vale. A ação precisa estar na lista do runbook, quem define se precisa de aprovação é o runbook, e o modelo não consegue reduzir a severidade do alerta nem escolher um runbook que não recebeu. Tudo isso é coberto por testes. |
| **Busca híbrida com Reciprocal Rank Fusion** | Alertas misturam identificadores exatos (`event 4625`, `vfs.fs.size[C:,pfree]`, IDs de regra) com texto livre. O BM25 acerta os identificadores e os vetores acertam as paráfrases. O RRF junta os dois rankings sem precisar calibrar as notas de cada um. |
| **"Não sei" é uma resposta válida** | Se a evidência textual é fraca, nenhum runbook é aceito e o alerta é escalado. Uma resposta errada e confiante às 3 da manhã é pior que acordar alguém. |
| **Motor determinístico de contingência** | Se o modelo cair ou devolver JSON inválido, um motor baseado nas regras dos runbooks responde no lugar. A triagem perde qualidade, mas não para. |
| **Texto do alerta é entrada não confiável** | O conteúdo do alerta vai para o modelo marcado como dado, e o prompt manda ignorar instruções dentro dele. O conjunto de avaliação tem um caso de prompt injection. |
| **O agente nunca executa nada** | Ação aprovada é entregue à ferramenta de RMM ou automação que já tem as credenciais. O agente não tem acesso de escrita aos sistemas dos clientes. |
| **Toda aprovação tem dono** | Cada aprovador tem um token pessoal. O nome na trilha de auditoria vem do token, não do que foi enviado na requisição, e a decisão trava a linha no Postgres para que duas pessoas não aprovem a mesma ação duas vezes. |
| **Independente de fornecedor** | API da Anthropic ou qualquer endpoint compatível com OpenAI (OpenAI, Azure OpenAI, Ollama, vLLM). Os embeddings também, com um embedder offline para o CI. |

## Avaliações

O `triage-evals` roda um conjunto de alertas rotulados (`evals/dataset.jsonl`). Ele cobre
paráfrases, payloads de cada fornecedor, alertas desconhecidos que precisam ser escalados e uma
tentativa de prompt injection. Se uma métrica cai abaixo do limite, **o build falha**.

| Métrica | Motor por regras | Limite |
|---|---|---|
| acerto da busca no 1º lugar | 1.00 | 0.85 |
| acerto da busca no top 3 | 1.00 | 0.95 |
| runbook correto (ponta a ponta) | 1.00 | 0.85 |
| severidade correta | 1.00 | 0.85 |
| alertas desconhecidos escalados | 1.00 | 1.00 |
| trava de aprovação respeitada | 1.00 | 1.00 |

O conjunto é pequeno (22 casos) e sintético: serve para barrar regressão, não como benchmark. Um
dos casos veio do teste no Kubernetes: um alerta curto do Wazuh que a primeira fórmula de
ranking mandava para o runbook errado. Ele entrou no conjunto para o erro não voltar.
Para rodar a mesma bateria contra um modelo real:

```bash
LLM_PROVIDER=anthropic LLM_API_KEY=... triage-evals
```

## Como rodar

```bash
# local, sem internet e sem chave de API
uv venv && uv pip install -e ".[dev]"
pytest && triage-evals
uvicorn triage.api:create_app --factory --port 8080

# stack completa com Postgres + pgvector
cp .env.example .env
docker compose up --build
curl -X POST localhost:8080/alerts/zabbix -H 'X-API-Key: change-me' \
     -H 'content-type: application/json' -d @examples/zabbix-disk.json
```

A documentação interativa da API fica em `http://localhost:8080/docs`.

### API

| Método | Caminho | Para que serve |
|---|---|---|
| POST | `/alerts/zabbix` | Webhook do Zabbix (media type) |
| POST | `/alerts/wazuh` | Integração do Wazuh |
| POST | `/alerts` | Alerta genérico já normalizado |
| GET | `/triage/{id}` | Resultado da triagem com citações e notas das travas |
| GET | `/approvals` | Ações aguardando uma pessoa |
| POST | `/approvals/{id}` | Aprovar ou rejeitar uma ação. Exige `X-Approver-Token` |
| GET | `/audit` | Quem aprovou ou rejeitou o quê, e quando |
| GET | `/healthz`, `/readyz` | Verificações de saúde |

Os webhooks são autenticados por um segredo compartilhado no cabeçalho `X-API-Key`. Aprovar exige
também um token pessoal (`APPROVER_TOKENS="alice:token,bob:token"`); sem ele as aprovações ficam
desligadas. Os tokens são comparados em tempo constante. Com `DATABASE_URL`, triagens e trilha de
auditoria ficam no Postgres e sobrevivem a reinícios; sem ele, tudo fica em memória (uma réplica só).

## Deploy

* **Container**: `Dockerfile` em dois estágios, roda sem root e é publicado no GHCR pelo CI.
* **Kubernetes**: chart Helm em `deploy/helm/triage-agent`. Tem sistema de arquivos só de
  leitura, remove todas as capabilities, usa HPA e lê os segredos de um Secret já existente
  (External Secrets, Sealed Secrets, operador do Infisical). Inclui probes e ingress opcional.
* **AWS**: Terraform em `infra/terraform/aws`. Cria uma VPC e um nó k3s único com IMDSv2, disco
  gp3 criptografado e **sem SSH** (acesso só pelo Session Manager). HTTPS fica liberado só para
  os servidores de monitoramento, e a API do Kubernetes só para as faixas de administração.

```bash
cd infra/terraform/aws
terraform init && terraform apply -var-file=example.tfvars
helm upgrade --install triage deploy/helm/triage-agent --set ingress.enabled=true
```

## CI

O GitHub Actions roda a cada push e pull request:
1. lint e formatação com ruff, com dependências instaladas do `uv.lock`
2. testes unitários e **testes de integração com Postgres/pgvector** num container de serviço
3. avaliações com limite mínimo, com o relatório publicado no resumo do job
4. `pip-audit` nas dependências travadas
5. `terraform fmt`/`validate`, `helm lint`/`template`
6. **teste ponta a ponta no Kubernetes**: cluster kind com Postgres, chart Helm com 2 réplicas e
   `scripts/smoke.py` passando pelo Service (webhooks, autenticação, aprovações, auditoria)
7. varredura da imagem com Trivy (falha em HIGH/CRITICAL com correção disponível) e push no GHCR na `main`

As actions são fixadas por SHA do commit e o Dependabot mantém Python, Actions e Docker
atualizados. O modelo de segurança está em [SECURITY.md](SECURITY.md).

Para rodar as mesmas verificações na sua máquina:

```bash
pytest && triage-evals
docker compose up -d --build && python scripts/smoke.py http://localhost:8080 change-me change-me-approver-token
./scripts/e2e-kind.sh   # precisa de kind, kubectl e helm
```

## Estrutura

```
src/triage/
  normalize.py        payloads do Zabbix / Wazuh -> Alert
  retrieval/          divisão em trechos, BM25, embeddings, bancos vetoriais (memória, pgvector), fusão RRF
  llm.py, prompts.py  motores de decisão (Anthropic, compatível com OpenAI, regras)
  agent.py            buscar -> decidir -> aplicar travas
  approvals.py        repositórios (memória, Postgres), tokens de aprovador, auditoria, Telegram
  db.py               trava consultiva para as réplicas não disputarem a criação do schema
  api.py              aplicação FastAPI
  evals.py            avaliações com limite mínimo
runbooks/             runbooks em Markdown com cabeçalho YAML (ações e flags de aprovação)
evals/                conjunto rotulado e último relatório
deploy/helm/          chart Helm
deploy/e2e/           Postgres só para o teste no kind
scripts/              smoke test e script ponta a ponta no kind
infra/terraform/aws/  VPC + nó k3s, acesso por SSM
```

## Próximos passos

- Botões no Telegram para aprovar com um toque (hoje o Telegram só avisa).
- Webhooks assinados ou mTLS no lugar da chave compartilhada.
- Janela de correlação: agrupar alertas do mesmo site antes da triagem (uma queda de VPN não
  deveria gerar 12 chamados).
- Avaliação da qualidade do resumo com um modelo como juiz, junto das métricas determinísticas.

Autor: **Vinicius Dutra**. [LinkedIn](https://www.linkedin.com/in/viniciusdutra-vnctec) ·
[Portfólio](https://viniciusdutra.netlify.app)
