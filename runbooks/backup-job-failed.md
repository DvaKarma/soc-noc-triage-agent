---
id: backup-job-failed
title: Backup job failed or did not run
sources: [zabbix]
keywords: [backup, vzdump, job failed, backup failed, snapshot, restore, retention, acronis, proxmox backup, last backup age]
default_severity: medium
actions:
  - name: read_backup_log
    description: Read the last job log and the storage free space at the backup destination.
    requires_approval: false
  - name: rerun_backup_job
    description: Re-run the failed job outside business hours.
    requires_approval: true
  - name: run_restore_test
    description: Restore one sample file or VM to an isolated location and verify it opens.
    requires_approval: false
---
## Symptoms
The scheduled job reports failure, or the age of the last successful backup exceeds the policy.

## Diagnosis
Check whether the alert is real: jobs that only run on weekdays look "late" on Monday mornings if
the age threshold ignores the schedule. Then check destination space, locks left by a previous run,
and whether the source path still exists (a moved folder makes the job succeed while copying nothing).

## Remediation
Fix the cause and re-run the job. A backup is only trusted after a restore test that opens real files.

## Escalation
Escalate if no valid restore point exists for more than 48 hours.
