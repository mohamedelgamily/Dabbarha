# Backup, retention and restore procedure

Status: design and runbook only. Backup retention, encryption, WAL archiving,
object storage, and restore drills have not been configured or tested against a
production service.

## Proposed objectives

Proposed initial recovery objectives for owner review:

- **RPO:** at most 15 minutes of committed database writes lost.
- **RTO:** restore verified core API/database service within 4 hours.
- **Backup retention:** encrypted backups expire no later than 30 days, matching
  the approved account-deletion disclosure decision.
- **Restore test:** monthly automated integrity checks plus a full isolated
  restore exercise at least quarterly and before major schema/data changes.

These targets are not measured or promised. Production owners must confirm they
fit the provider, region, budget and legal policy. If the selected provider
cannot meet them, obtain an explicit objective change before launch.

## Backup design

Use managed PostgreSQL point-in-time recovery when available, and an independent
encrypted logical backup to a separate private object-storage account. Enable
continuous WAL archiving or provider-native PITR with a verified recovery
window. Schedule at least daily logical exports; protect the encryption key in
a separate KMS/secret-management domain with tightly controlled recovery.
Enable object versioning/immutability only if automatic deletion still enforces
the 30-day maximum; an indefinite legal hold is an explicit privacy exception,
not a silent default.

Encrypt data in transit and at rest. Store backup encryption keys separately
from the backup objects and application secrets. Require MFA and dual approval
to export, restore or change retention. Keep staging and production backup
locations and encryption keys separate. Do not include application `.env`
files, deployment secrets, Redis snapshots, test fixtures or logs in database
backups. Maintain a separate encrypted secret-recovery procedure with its own
retention and access review.

Retain PostgreSQL base/managed backups and WAL only within the approved 30-day
maximum. Configure deletion expiration, verify actual object/version deletion,
and alert on any item that exceeds the window. Provider-native PITR windows may
be shorter; the independent backup plus WAL plan must meet the approved RPO/RTO
without extending personal data beyond 30 days. Confirm snapshots, exports,
replicas and provider support artifacts are also covered by the retention
policy.

Redis contains short-lived rate-limit keys, not authoritative user or financial
records. It may be rebuilt empty after an outage; doing so resets active quotas,
so a restore/restart must be monitored. Do not treat the limiter as a database
backup target. Never restore Redis state from another environment.

## Restore quarantine (required because accounts are hard-deleted)

The application does not retain a user-linked deletion ledger. A database
snapshot from before a deletion can therefore restore that account and its
sessions. **Never place a snapshot-only restore directly into service.** A safe
restore must use a new isolated database/network, restore the base backup, replay
all WAL/post-backup changes through the latest verified recovery point, verify
that account deletions are included, check constraints/orphan rows, then run
smoke tests before changing service credentials to the restored database.

If complete WAL or deletion history is unavailable, keep the restored system
quarantined and do not expose it to users. Escalate to the privacy and incident
owners. A keyed-HMAC deletion journal could mitigate incomplete replay but would
be a pseudonymous user-linked retention store and requires separate privacy
approval; it is not implemented in this phase.

## Restore drill

Use a dedicated disposable recovery project with no route from production. The
drill must:

1. Select a timestamped backup and verify its checksum, encryption metadata and
   recoverable key version without printing credentials.
2. Restore into a fresh isolated PostgreSQL instance; retain the source backup.
3. Apply WAL through a known point after a synthetic account is deleted. Prove
   the deleted account, its obligations, sessions, notification rows and tokens
   are absent after replay. Never use a real account as a test marker.
4. Verify Alembic revision, table/index/constraint counts, foreign keys, sequence
   behavior, row counts and representative financial schedule totals against
   synthetic expected data.
5. Run `pip check`/application smoke checks against the isolated restore without
   external push delivery. Verify that the database remains private and the app
   uses temporary credentials only.
6. Measure actual recovery time and recovery-point gap; compare with approved
   RTO/RPO. Confirm no secrets, personal records or backup URLs entered logs.
7. Destroy the temporary database and drill credentials, record evidence and
   verify backup expiration still works.

Repeat a full drill before production launch, after PostgreSQL major upgrades,
after backup-policy changes and after any migration with significant data
effects. An operator should be able to run the drill without access to ordinary
application logs containing user data.

## Backup incident response

On a missing/late backup or WAL gap, alert the service owner and block release.
On accidental deletion or corruption, stop dangerous writes if safe, preserve
the current database and logs, restore to an isolated instance, replay changes
and verify account deletions. Record the point-in-time and any accepted data
loss with the incident owner. Switch traffic only after integrity and privacy
checks pass and the old database remains recoverable.

Do not claim the approved 30-day encrypted-backup retention is operational
until the provider's configuration, secondary copies, expiration job and actual
deletion evidence are reviewed. Do not claim backup/restore validation until a
timed restore drill has passed.
