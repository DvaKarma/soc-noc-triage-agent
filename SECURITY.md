# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/DvaKarma/soc-noc-triage-agent/security/advisories/new).
Do not open a public issue. You can expect a first answer within 5 business days.

## Security model

- The agent **never executes actions**. It proposes; approved actions are handed to an external
  RMM/automation platform. It holds no credentials for client systems.
- Webhooks require a shared `X-API-Key`. Approvals require a **personal** `X-Approver-Token`;
  the identity in the audit trail comes from the token, never from the request body.
- Approval flags and the action allowlist come from the runbooks and are enforced in code;
  model output cannot bypass them. Alert content is treated as untrusted input.
- Supply chain: locked dependencies (`uv.lock`), `pip-audit`, Trivy image scan, actions pinned
  by commit SHA, Dependabot.

## Known limitations

- Rate limiting is expected at the ingress / reverse proxy, not in the app.
- Shared-secret webhook auth; mTLS or signed webhooks are on the roadmap.
