---
id: tls-certificate-expiring
title: TLS certificate expiring or renewal failing
sources: [zabbix]
keywords: [certificate, ssl, tls, expiring, expires, expiry, lets encrypt, acme, renewal, http-01, https, web.certificate]
default_severity: medium
actions:
  - name: inspect_certificate
    description: Read the certificate chain, expiry date and the ACME renewal log.
    requires_approval: false
  - name: switch_to_dns_challenge
    description: Reissue the certificate using the DNS-01 challenge.
    requires_approval: true
---
## Symptoms
A public endpoint certificate expires in less than 14 days, or the reverse proxy logs renewal errors.

## Diagnosis
HTTP-01 renewal fails when port 80 is blocked or redirected before the ACME path. Check the proxy
config and the firewall. Confirm whether the certificate is used by other services (mail, VPN).

## Remediation
Open the challenge path or move to DNS-01, renew, and reload the proxy without downtime.

## Escalation
Escalate if expiry is under 3 days or the endpoint is customer facing.
