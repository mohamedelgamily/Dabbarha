# Deployment and release runbook

Status: procedure prepared for review. No staging or production environment has
been created, and no deployment or persistent migration was run.

## Release invariants

- Target runtime: Ubuntu Server 24.04 LTS, x86_64, current supported security
  patch of CPython 3.12. Record the exact patch and OS image digest per release.
- Build from the reviewed Git commit. Use `requirements-linux-py312.lock` with
  hashes; do not install from the range-based `requirements.txt` in production.
  Build once in a clean Linux x86_64 environment, run `pip check` and `pip-audit`,
  and promote the identical immutable artifact from staging.
- Run one API service and one independently supervised notification worker. Do
  not start the worker from API lifespan or run multiple worker schedulers
  without verifying the database locking and idempotency behavior.
- PostgreSQL and shared private Redis are mandatory for production. SQLite and
  memory rate limits are development/test only. Do not deploy until the managed
  Redis hostname compatibility gate in [the architecture decision](production-architecture.md)
  is resolved.
- Do not make the API process run Alembic at startup. Use a one-shot release
  job with a migration-only database credential.

## Environment preparation

Create separate staging and production resources. Give each environment a
separate PostgreSQL database/cluster, Redis instance, database roles, domain,
secret scope, Expo project/credential set and deploy permissions. Staging
accounts and records must be synthetic. Do not copy actual `.env` files into a
platform dashboard or use production credentials in staging.

Use `/etc/dabbarha/api.env` only for the API and `/etc/dabbarha/worker.env` only
for the worker; the inactive [`deploy/worker.env.example`](../deploy/worker.env.example)
documents the worker variables. The worker does not require `JWT_SECRET_KEY`,
rate-limit HMAC, refresh receipt, or admin TOTP keys. Give it the push-token
encryption key and optional Expo credential only when notifications are enabled.
Give API, worker and Alembic release job separate PostgreSQL roles. The API
runtime role needs reviewed application DML and account-deletion cascades, but
no schema ownership or DDL. The worker role needs only the reads/writes for
`users` (bounded account lock), `obligations`, `obligation_installments`,
`notification_preferences`, `payment_occurrences`, `payment_occurrence_events`,
`notifications`, `notification_deliveries`, `notification_devices`,
`auth_sessions`, and `worker_heartbeats`, plus sequence use for its insert tables.
It must not read refresh-token, admin, financial-support, or unrelated user data
tables. Derive exact column grants from current worker queries and test the role
against scheduling, retries, receipts, deletion locks and heartbeat writes in
disposable PostgreSQL before deployment. Migration credentials are used only
by the release job.

Provision each secret through the chosen platform's secret manager or a root-
controlled service credential mechanism. `.env.production.example` has blank
secret values by design and is not an operational environment file. Never commit
real values. Do not paste secrets into shell history, issue text, build args,
logs, screenshots or release notes. Confirm production and staging secret values
are distinct without printing them.

Before service launch, explicitly review: `APP_ENV=production`, docs disabled,
PostgreSQL URL with verified TLS, Redis backend and private endpoint, separate
JWT/limiter/receipt/push/admin keys, session rollout flags, notification flags,
admin default-off, worker-only environment and Caddy/proxy trust. Keep session,
notification and admin features disabled unless their migration, mobile
integration, key provisioning and operational controls have each passed their
own rollout review. Do not silently rotate existing keys.

## Build and pre-deploy checks

On a clean Linux x86_64 builder, use the pinned lock and do not update pip during
the deployment build:

```sh
python3.12 -m venv /opt/dabbarha/build-venv
/opt/dabbarha/build-venv/bin/python -m pip install --only-binary=:all: --require-hashes -r requirements-linux-py312.lock
/opt/dabbarha/build-venv/bin/python -m pip check
```

Run `pip-audit --path <build-venv-site-packages> --strict` using a separately
provisioned, reviewed scanner environment; do not install audit tools ad hoc in
the production runtime or update pip during the deployment build. The actual
pinned environment and vulnerability scan are validated by the external Phase
2g.2 runner on the operator's Mac; Linux package installation must also be
verified in the chosen Linux CI/build environment before launch.

Verify the artifact contains no `.env`, database files, logs, test data or
secrets. Record commit SHA, image digest, lock hash, test log, security scan,
SBOM if available, and approver in the release record. Do not expose CI logs
containing environment dumps.

## Database migration release

1. Verify target identity using a secret-safe environment inventory. Confirm the
   `DATABASE_URL` points to the intended **staging** database and that the
   runtime role is not being used for migration.
2. Take a provider snapshot/PITR restore point and an encrypted logical backup.
   Verify the backup can be read and restore it into an isolated disposable
   database before relying on it.
3. Review every pending Alembic revision and SQL operation. Check `alembic
   heads`, `alembic current` and `alembic history`; ensure a single expected head.
   Search revisions for table drops, data rewrites, locks and unbounded updates.
4. On staging, run `alembic upgrade head` once with the migration credential.
   Verify revision, indexes, constraints, row counts and core smoke tests. Test
   rollback only on disposable databases; do not assume a downgrade is safe on
   production data.
5. Run the application artifact against migrated staging and complete
   [production smoke tests](production-smoke-tests.md). Keep the old app artifact
   available.
6. For production, take and verify a new backup immediately before the approved
   migration window. Run the migration as a single controlled job, watch locks
   and duration, verify the resulting revision, then deploy API and worker.
   Production migration execution requires a separate explicit approval and is
   not authorized by this runbook.

## Deploy and verify

Deploy API first, then worker after the API and migration checks pass. Use
separate service identities and environment scopes. For the systemd/Caddy
single-host example, validate the Caddyfile, Uvicorn proxy peer, service units,
file permissions, socket group, firewall and restart behavior before enabling
traffic. For a platform, verify it uses same-region private endpoints and its
actual proxy peer matches the configured trust boundary.

The PostgreSQL engine pool is limited to 5 connections plus 2 overflow per
process, waits at most 10 seconds, recycles after 30 minutes and checks stale
connections before use. Budget up to `API replicas × Uvicorn workers × 7 +
worker processes × 7 + migration processes × 7`, plus admin/monitoring tools.
The example two-worker API and one worker can open 21 connections; allow up to
28 during a migration overlap. Recalculate if deployment process counts change.
The inactive systemd examples do not set fixed `MemoryMax`, `CPUQuota` or
`TasksMax` values because the VPS/provider size and measured workload are not
selected. Before launch, set and test per-service CPU, memory and process limits
with staging load measurements, leaving sufficient headroom for database
connections, Argon2 work, Redis, and safe shutdown. Do not copy arbitrary limits
from a development host.

Use `/health` only for process liveness. In production, `GET /ready` requires a
PostgreSQL connection (SQLite remains valid for local development/tests), checks
`SELECT 1`, requires
the database `alembic_version` rows to match the packaged migration heads, and
pings Redis when the configured limiter backend is Redis. It returns only
`{"status":"ready"}` or a generic 503 `{"status":"unavailable"}` with
`Retry-After`; it exposes no component names, hostnames or driver errors. It is
not an admin API and remains undocumented in OpenAPI. Restrict probe traffic at
the ingress where possible. DB checks use bounded engine connection/pool
timeouts and PostgreSQL statement/lock timeouts; Redis DNS, connect and socket
operations are bounded. Continue to use a scheduled authenticated synthetic
transaction against disposable/staging accounts for end-to-end coverage. Never
use financial values or secret credentials as probe payloads.

Complete the smoke checklist in staging before production. In production,
perform only non-destructive checks against a designated test account and only
after a release owner approves the account and deletion test. Do not create or
delete real customer accounts as a smoke test.

## Rollback and recovery

Rollback application code by redeploying the prior immutable artifact. Additive
schema revisions may remain in place if the old application is compatible;
verify this from the migration review. Do not automatically run `alembic
downgrade` during incident rollback. A downgrade can destroy user data or make
the prior application incompatible.

If a migration is not backward compatible, pause rollout before execution and
prepare a forward-fix or isolated database restore plan. Restore into a new,
isolated database and reconcile post-backup writes and account deletions before
switching service URLs. Do not overwrite the only production copy. See
[backup and restore](backup-and-restore.md).

After rollback, verify API liveness, protected read/write recovery, notification
worker heartbeat/delivery state, session validity, Redis enforcement, migration
revision and alert clearance. Record impact, timestamps, artifact/DB revisions,
recovery decision and follow-up tasks without including personal or financial
values.

## VPS configuration template

`deploy/dabbarha-api.service.example`,
`deploy/dabbarha-notifications.service.example`,
`deploy/Caddyfile.example` and `deploy/redis.conf.example` are inactive examples
for a single-host Caddy + loopback API + local Unix-socket Redis layout. They do
not provision PostgreSQL or represent managed-PaaS configuration. Review
service users, directories, Uvicorn version, process count, proxy peer, Redis
socket group and secret-loading mechanism before use. The examples are not
production-approved deployment artifacts.
