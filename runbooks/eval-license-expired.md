---
id: eval-license-expired
title: Windows Server shutting down because the evaluation license expired
sources: [zabbix, wazuh]
keywords: [unexpected shutdown, shut down, powered off, evaluation, license, expired, wlms, event 1074, event 6008, server down, host unreachable overnight, activation]
default_severity: critical
actions:
  - name: read_event_log
    description: Read System log events 1074, 6008 and WLMS entries around the shutdown time.
    requires_approval: false
  - name: rearm_evaluation
    description: Run slmgr /rearm to buy time while the definitive license is purchased.
    requires_approval: true
  - name: convert_to_licensed_edition
    description: Convert the evaluation edition with a valid product key (DISM /Set-Edition).
    requires_approval: true
---
## Symptoms
A server powers off by itself, often at night, roughly every hour after the first shutdown. In the
morning nobody can log in and shared folders are unavailable. Hardware, power and storage look fine.

## Diagnosis
The System event log shows the Windows License Monitoring Service (WLMS) initiating shutdowns and
event 1074 with the license reason. `slmgr /dlv` reports an Evaluation channel with zero time left.
Also verify that monitoring notifications are delivered: a wrong recipient address or blocked SMTP
means the alerts existed but nobody received them.

## Remediation
Bring the client back with a temporary rearm, then convert to a licensed edition. Check every other
server in the fleet for the same evaluation channel and its remaining days.

## Escalation
Always escalate: it is a business outage and it involves a licensing purchase decision.
