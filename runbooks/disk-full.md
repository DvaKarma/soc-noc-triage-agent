---
id: disk-full
title: Disk space critical on server
sources: [zabbix]
keywords: [disk, free space, filesystem, storage, vfs.fs.size, volume, drive, full, pfree, low space]
default_severity: high
actions:
  - name: collect_disk_usage
    description: List the largest folders and the growth of temp, log and backup staging paths.
    requires_approval: false
  - name: clean_temp_files
    description: Delete temp files and rotated logs older than 7 days (whitelisted paths only).
    requires_approval: true
  - name: extend_volume
    description: Extend the virtual disk and the partition after a snapshot.
    requires_approval: true
---
## Symptoms
Free space on a system or data volume is below 10 percent. Applications that write temp files
(ERP, billing, databases) slow down or freeze at peak hours, and users usually blame "the system".

## Diagnosis
Check which path grew. Usual causes: temp folders, rotated logs that never get deleted, old local
backup copies, Windows Update cache, database transaction logs without truncation. Compare with
the growth trend for the last 30 days before deciding whether to clean or to extend.

## Remediation
Clean only whitelisted temp and log paths. If growth is legitimate data, extend the volume after
taking a snapshot. Add a predictive trigger (time to full under 7 days) so it never reaches 100 percent.

## Escalation
Escalate if the volume hosts a database or a domain controller, or if free space is under 2 percent.
