---
id: agent-unreachable
title: Monitoring agent or host unreachable
sources: [zabbix]
keywords: [unreachable, unavailable, agent not available, no data, nodata, zabbix agent, icmp, ping, host down, proxy, timeout, offline]
default_severity: medium
actions:
  - name: check_connectivity_path
    description: Test ICMP and agent port from the proxy and check VPN routes for the client site.
    requires_approval: false
  - name: restart_monitoring_agent
    description: Restart the monitoring agent service through the RMM.
    requires_approval: true
---
## Symptoms
A host stops sending data or the agent becomes unavailable. Several hosts of the same site going
silent at once points to the network path, not to the hosts.

## Diagnosis
Test from the proxy that monitors the site. Look for a VPN pushing a route that overlaps the local
LAN, a proxy that was upgraded but never restarted, or an agent that crashes at start-up. Check if
the machine is simply powered off (workstations) before opening an incident.

## Remediation
Fix the route or restart the agent. Add a dependency so one site failure does not page per host.

## Escalation
Escalate if a server stays unreachable for more than 15 minutes during business hours.
