---
id: memory-pressure
title: Memory pressure and high swap usage
sources: [zabbix]
keywords: [memory, swap, ram, oom, out of memory, available memory, pressure, page file, memory leak]
default_severity: medium
actions:
  - name: top_memory_consumers
    description: List processes and containers by resident memory and their growth over 24h.
    requires_approval: false
  - name: restart_leaking_service
    description: Restart the service identified as leaking memory.
    requires_approval: true
---
## Symptoms
Available memory under 10 percent and swap usage growing; latency rises and the OOM killer may stop processes.

## Diagnosis
Separate a leak (steady growth of one process) from undersizing (many processes, flat growth).
Containers without memory limits are a common cause on shared hosts.

## Remediation
Restart the leaking service and open a ticket with its owner, or set memory limits and resize.

## Escalation
Escalate if the OOM killer stopped a database or the host is a hypervisor.
