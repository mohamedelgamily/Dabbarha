# Administrator operational APIs (Phase 2f.2)

Phase 2f.2 adds read-only service operations and bounded account metadata lookup.
It does not implement the browser dashboard, financial-record inspection, or
support grants. Phase 2f.3 support inspection remains pending.

## Authentication and permissions

Every route below requires `ADMIN_API_ENABLED=true`, an account provisioned as
`admin` or `superadmin` through the Phase 2f.1 offline command, a live durable
v2 device session, and a fresh Phase 2f.1 TOTP step-up token. Regular access JWTs
and legacy JWTs do not authorize these endpoints. Current database role and
session state are checked for every request. Admins and superadmins have the
same Phase 2f.2 operational permissions; neither role can see an individual
financial profile, obligation, installment amount, payment amount, or private
notification content. No impersonation or write action is available.

Admin requests use configurable Redis-backed quotas: `RATE_LIMIT_ADMIN` defaults
to 60 authenticated admin requests per account per minute and
`RATE_LIMIT_ADMIN_IP` defaults to 120 admin requests per client IP per minute.
The existing IP rate-limit middleware is the only source of client IP;
forwarded headers are accepted only when Uvicorn is configured with explicit
trusted proxies. Redis failures fail closed with HTTP 503. Access and denied
attempts are added to `admin_audit_events` when audit storage is available. Audit
records contain bounded action/outcome values, optional user IDs and an HMAC
source fingerprint; they never include request text, IP, tokens, or private data.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /admin/ops/overview?window_days=7` | Account, aggregate obligation, notification queue, worker, and error-category metrics. `window_days` is 1–30. |
| `GET /admin/ops/health` | API, database, Redis, worker, migration and non-secret configuration-readiness status. |
| `GET /admin/users/lookup?user_id=123` | Exact numeric account lookup. |
| `GET /admin/users/lookup?email=person%40example.test` | Exact normalized email lookup; wildcard syntax is rejected. Provide exactly one lookup key. |
| `GET /admin/users/{user_id}/sessions?limit=50&offset=0` | Bounded page of safe session/device metadata. Limit is 1–100 and offset is capped. |
| `GET /admin/users/{user_id}/deliveries?state=failed&after_id=0&limit=50` | Bounded, user-scoped delivery diagnostics. |
| `GET /admin/notifications/deliveries?state=failed&after_id=0&limit=50` | Bounded global delivery diagnostics for operational investigation. |

User lookup returns only account ID, display name, email, registration timestamp,
admin role and `account_state: "present"`. The backend has no suspension state;
the response says so explicitly. Deleted accounts are hard-deleted and return
404. Session responses can include session IDs, device label/platform, active
state and lifecycle timestamps. They never include access/refresh tokens, token
hashes, TOTP material, encryption keys or push tokens.

Delivery diagnostics return delivery/notification IDs, account ID, notification
type, state, platform, attempt counts, timestamps and a normalized error
category. They omit notification title/body, provider references, push tokens,
and raw provider error strings. Unknown provider errors are grouped as `other`.
Pages return `next_cursor` when another ID page exists. Limits above 100 are
rejected. There is no retry or mutation endpoint: a provider timeout may leave
acceptance ambiguous, and manual retry could duplicate a push.

## Metric definitions and limitations

The overview defaults to a seven-day window and accepts at most 30 days:

- `accounts.total` counts rows currently in `users`.
- `accounts.registered_in_window` counts registration timestamps in the selected
  window.
- `accounts.recently_refreshed_v2_session_accounts` counts distinct users with
  a non-revoked, non-expired v2 session that has had at least one refresh
  (`current_generation > 0`) and was actually refreshed during that same
  window. Newly issued sessions alone do not count. This is explicitly a
  session-activity indicator, not a measure of a person using the app.
- `accounts.deletions_in_window` is `null`, with `deletions_available: false`,
  because approved hard deletion retains no deletion ledger. It is never
  represented as zero or inferred from unrelated records.
- `obligations_total` counts all current obligation rows, without summing or
  returning any amount.
- Notification state counts are delivery rows, not parent notification rows.
  `pending` and `queue_size` mean queued plus sending deliveries; `accepted`
  combines provider-accepted and platform-accepted rows; failed and cancelled
  are separate. `oldest_pending_age_seconds` uses delivery creation time, and
  `stale_sending_count` counts expired sending leases.
- Failed delivery error summaries are current failed rows grouped into a small
  safe category set. They are not a historical error-event stream.
- Worker heartbeat is updated at each completed worker cycle, including a
  bounded generic failure category. `available` means a recent successful
  heartbeat without a later failed cycle; `degraded` means a recent failed
  cycle; `stale` means no heartbeat within `max(60 seconds, 3 × configured poll
  interval)`; `unknown` means no heartbeat has been recorded; `disabled` means
  notifications are disabled.

The heartbeat table contains no user IDs, account linkage, hostnames, process
IDs, or provider details. It is an additive migration and is updated by the
existing separately supervised worker. If the worker cannot reach the database,
it cannot refresh its heartbeat, so status becomes stale. PostgreSQL operational
queries use a three-second statement timeout; connection establishment is
bounded to five seconds. Redis health checks use the configured Redis socket
timeout. Health failures return a controlled status or 503; database errors and
connection strings are never included in responses. A database outage may block
session authentication before the health handler runs and yield a safe 503.

Heartbeat instants are UTC-aware in application code. PostgreSQL stores them in
`TIMESTAMP WITH TIME ZONE`; reads are converted to UTC regardless of the
connection's configured timezone. SQLite drops timezone metadata for these
columns, so naive values read from SQLite are interpreted as UTC by convention.
Health responses serialize both heartbeat timestamps with a UTC `+00:00` offset.
When a cycle fails, `last_seen_at` is that failed cycle's timestamp while
`last_error_category` is present; `last_success_at` remains the prior successful
cycle. After a later successful cycle, the current error category clears. The
v1 heartbeat does not retain a separate historical last-failure timestamp.

`GET /admin/ops/health` may return `status: "degraded"` while reporting an
unavailable component. If Redis is down, the fail-closed request limiter can
reject the health request itself with 503; use external infrastructure
monitoring to diagnose that case. Migration revision is read from Alembic's
`alembic_version` table; an absent/unreadable version is `unknown`, not guessed.
Configuration readiness returns boolean state only, never secret values or
connection URLs.

## Safe response examples

```json
{
  "accounts": {
    "total": 82,
    "registered_in_window": 7,
    "deletions_in_window": null,
    "deletions_available": false,
    "deletions_reason": "Hard deletion leaves no retained account-linked event; deletions are not measured.",
    "recently_refreshed_v2_session_accounts": 24,
    "recent_session_window_days": 7
  },
  "obligations_total": 190,
  "notifications": {
    "queue_size": 3,
    "pending": 3,
    "accepted": 16,
    "failed": 2,
    "cancelled": 1,
    "oldest_pending_age_seconds": 44,
    "stale_sending_count": 0,
    "failed_error_categories": [{"category": "temporary_provider_failure", "count": 2}]
  },
  "worker": {"state": "available", "last_seen_at": "2026-10-22T09:00:00+00:00", "last_success_at": "2026-10-22T09:00:00+00:00", "last_error_category": null, "cycles": 1234}
}
```

Values above are illustrative only. Account and delivery identifiers in real
responses are sensitive operational metadata and should not be written to
browser analytics or general application logs.

## Errors and operational requirements

- `401`: missing, invalid, expired or revoked v2 session.
- `403`: account lacks an operational admin role or fresh MFA step-up.
- `404`: disabled admin API or an account that does not exist.
- `422`: invalid lookup shape, wildcard, pagination or window value.
- `429`: rate quota exceeded; honor `Retry-After`.
- `503`: Redis, database, or audit storage is unavailable or bounded query work timed out.

Before enablement, deploy the reviewed additive migration and configure shared
private Redis, durable sessions, TOTP encryption key, role provisioning, and
external API/database/Redis/worker monitoring. Configure the agreed audit
retention and alerts through deployment operations after privacy/legal review.
This phase does not implement retention enforcement, alerts, production service
provisioning, or production migration.

Phase 2f.3 financial support inspection remains pending. It must use a specific
target, reason and case reference, fixed read-only data scope, recent MFA,
maximum 15-minute grant, pagination, no export, and enhanced auditing. A
superadmin role alone must never permit financial-data access.
