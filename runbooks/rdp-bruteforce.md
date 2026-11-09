---
id: rdp-bruteforce
title: Brute-force attack against remote access (RDP or VPN)
sources: [wazuh]
keywords: [brute force, multiple failed logins, authentication failure, "event 4625", rdp, remote desktop, "3389", sshd, failed password, logon failure, rule 60122, rule 60204, srcip]
default_severity: high
actions:
  - name: enrich_source_ip
    description: Look up reputation, geolocation and how many hosts the source IP hit.
    requires_approval: false
  - name: block_source_ip
    description: Block the source IP on the edge firewall for 24 hours.
    requires_approval: true
  - name: disable_exposed_rdp
    description: Remove the public RDP port forward and require VPN.
    requires_approval: true
  - name: reset_targeted_account
    description: Force a password reset for an account that had a success after failures.
    requires_approval: true
---
## Symptoms
Hundreds of failed logons (Windows event 4625, sshd "Failed password") from one or a few external
IPs. Service may become unresponsive: RDP listening but not accepting sessions after a burst.

## Diagnosis
Confirm the service is exposed to the internet. Look for a successful logon (4624) from the same
source after the failures: that turns an attempt into an incident. Check whether accounts were locked.

## Remediation
Block the source, close direct exposure (RDP only through VPN), enable account lockout and MFA.
If the listener hung, restarting the Remote Desktop service restores access.

## Escalation
Escalate immediately if any logon succeeded from the attacking source or a privileged account was targeted.
