---
id: thin-pool-full
title: Hypervisor thin pool or datastore almost full
sources: [zabbix]
keywords: [thin pool, lvm, data percent, datastore, local-lvm, proxmox, vmware, overprovisioned, metadata, vm paused, io error]
default_severity: critical
actions:
  - name: report_pool_usage
    description: Report data and metadata usage per pool and the largest VM disks and snapshots.
    requires_approval: false
  - name: delete_old_snapshots
    description: Remove snapshots older than the retention policy.
    requires_approval: true
  - name: extend_thin_pool
    description: Extend the thin pool with free space from the volume group.
    requires_approval: true
---
## Symptoms
Thin pool data usage above 90 percent. When it reaches 100 percent, VMs freeze or go read-only and
domain services on them fail.

## Diagnosis
Find what consumed space: forgotten snapshots, VM disks without discard/TRIM, local backups stored
on the same pool. Check metadata usage too, it can fill before data does.

## Remediation
Free space or extend the pool, then run fstrim inside guests. Keep backups off the production pool.

## Escalation
Always escalate: a full thin pool can corrupt every VM on the host.
