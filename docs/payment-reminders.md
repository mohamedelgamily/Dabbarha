# Payment reminders and push notifications — Phase 2d

## Scope and rollout state

Dabbarha records financial plans and sends reminders; it does not collect payments
or verify bank transactions. A “paid” state means only that the signed-in user
declared that payment paid. Nothing in the API or copy represents a transfer,
settlement or provider confirmation.

The migration `2d1a00000001` adds notification and payment-occurrence tables. It
does not backfill old payment-completion claims or change the obligation status
field. Run it through the normal migration release after review; test upgrade,
downgrade and re-upgrade only against disposable databases. Downgrade deletes all
Phase 2d occurrences, audit events, preferences, tokens and notification history.

API startup never launches a worker or contacts Expo. `NOTIFICATIONS_ENABLED`
defaults to false. Push delivery also defaults to false and must be enabled
separately. Enabling the feature requires device-session authentication and a
separate push-token encryption key. Keep it disabled until the mobile app has
completed the documented session and push-registration handoff.

## Data model and payment accuracy

`payment_occurrences` stores a stable per-obligation occurrence key, exact due
date, amount snapshot, optional exact-installment reference, schedule version,
state, paid timestamp and reminder generation. A unique constraint prevents
duplicate occurrences. Occurrences are materialized lazily when a user opens a
bounded occurrence range or the worker schedules dates through the largest
configured reminder offset plus one day; the system does not precreate 1,200
rows for every plan.

Legacy monthly due dates follow the existing forecast's first payment month and
term. Their configured day is clamped to the last valid day of that month: day 31
becomes February 28 or 29 as applicable, and day 30 also becomes February 28 or
29. New installment plans use the exact persisted installment dates and amounts.
An unpaid down payment uses its saved exact date and amount; a down payment marked
paid is never projected as unpaid.

Occurrences default to `unpaid`. `POST
/obligations/{id}/payment-occurrences/{occurrence_id}/mark-paid` records a
user-confirmed declaration, writes a `marked_paid` audit event and cancels
queued/sending reminders. `POST
/obligations/{id}/payment-occurrences/{occurrence_id}/undo-paid` records an
`undone` audit event, increments the reminder generation and makes the occurrence
unpaid again. It only creates reminder events whose configured delivery times
are still in the future; it never replays expired offsets. The existing down
payment compatibility flag is updated in the same transaction.

Editing an installment plan uses the existing `schedule_version` compare-and-swap.
Pending occurrences are superseded and their queued notifications cancelled;
when the new schedule is synchronized, a matching due date is safely reused and
refreshed. Confirmed payment history and its saved amount/date remain intact.
The plan update endpoint cannot change a down payment's paid state directly; use
the occurrence Mark as paid or Undo paid action so the audit trail stays intact.
If a down payment is already paid, undo it before changing its amount or date.
Changed due dates create new occurrences. Completed/defaulted obligations and
deleted obligations stop producing reminders; deleted obligations' notification
history remains, with its deep-link reference cleared. Work already accepted by
Expo or a platform push service cannot be recalled.

## Preferences

`GET /notifications/preferences` creates and returns safe defaults on first
access. `PUT /notifications/preferences` replaces the preference object and
cancels queued events so the worker can rebuild them with current settings.

Defaults are reminders disabled, 7/3/1 days plus due day, 09:00, `Africa/Cairo`,
quiet hours 22:00–07:00, English, private lock-screen copy, overdue reminders
disabled, and upcoming/due-today categories. Supported categories are `upcoming`,
`due_today`, `overdue`, and `payment_completed`. Offset entries are selected from
7, 3, 1 and 0; duplicates and invalid time zones or wall-clock values are rejected.
Quiet-hour start/end must be supplied together; identical endpoints disable quiet
hours. The settings accept IANA zone identifiers and validate against Python's
zone database.

Reminder wall times are converted to UTC using the preference time zone. During
a daylight-saving gap, scheduling moves forward to the first valid local minute;
an ambiguous wall time uses its first occurrence. Quiet-hour reminders move to
the end of quiet hours. The worker drops stale pre-due notifications after the
due date and sends at most one same-day due reminder after a restart. An optional
overdue reminder is sent once on the day after its due date, only while the
occurrence remains unpaid. Missed older overdue events are not replayed.

## Push devices and session binding

Push-token endpoints require a version-2 authenticated device session:

- `POST /notifications/devices` registers an Expo token for the active session.
- `GET /notifications/devices` returns only device IDs, platform, active state
  and registration timestamps. It never returns a token.
- `PUT /notifications/devices/{device_id}` rotates a token and deactivates the
  old registration atomically.
- `DELETE /notifications/devices/{device_id}` deactivates the user's device.

Only syntactically valid Expo tokens for iOS or Android are accepted. Token
fingerprints enforce uniqueness; AES-256-GCM ciphertext is stored for provider
delivery, with associated data binding the ciphertext to user, session, token
fingerprint and key ID. Plaintext tokens are not returned or logged. A revoked,
expired or logged-out session is excluded by the delivery worker even if its
registration has not yet been cleaned up. Expo `DeviceNotRegistered` ticket or
receipt errors deactivate the token.

Do not reuse the JWT, rate-limit HMAC or refresh-receipt key for
`PUSH_TOKEN_ENCRYPTION_KEY`. This batch supports one active key ID; rotating that
key requires a planned decrypt-and-reencrypt operation with both old and new
keys. It does not change the JWT key or any existing credentials.

## Scheduler and delivery worker

The API process persists schedules and reads history but does not run timers. A
separate supervised process (`python -m app.commands.notification_worker`) does
the following in bounded cycles:

1. Materialize upcoming occurrences and deduplicated notification rows.
2. Create per-device delivery rows only for active, unrevoked sessions.
3. Claim deliveries with atomic conditional state updates. PostgreSQL serializes
   row updates across workers; SQLite's write transaction provides local test
   serialization. Unique constraints make occurrence, notification and device
   delivery creation idempotent.
4. Send through a replaceable provider adapter, then check Expo tickets and
   receipts. A ticket means Expo accepted the request; a successful receipt means
   APNs/FCM accepted it. Neither proves that the device displayed the message.
   The API uses `accepted` and `platform_accepted`, and never reports device
   delivery as confirmed by Expo.
5. Retry explicit transient HTTP/provider errors at most five times with bounded
   exponential backoff. A timeout or worker crash after a send begins has an
   ambiguous outcome; it is marked failed as unknown and is not resent, avoiding
   duplicate pushes at the cost of possibly losing one alert. Expo receipts are
   checked after 15 minutes and polled at bounded five-minute intervals.

The worker requires only the database for scheduling and coordination. It does
not depend on Redis availability and does not use in-memory timers or FastAPI
`BackgroundTasks`. Normal web rate limits remain governed by the existing Redis
configuration. `deploy/dabbarha-notifications.service.example` is a systemd
template, not an installed unit. Keep its environment file in a private secret
location and start the worker only after the feature rollout is approved.

`NOTIFICATION_DELIVERY_ENABLED=false` permits local schedule-generation tests but
prevents the worker from creating or sending push deliveries. Non-production
delivery is accepted only with `NOTIFICATION_PROVIDER=mock`; real Expo delivery
is production-only. The worker never runs automatically from the web app.

Send attempts are bounded and ticket receipts expire at Expo after 24 hours. The
worker retains notification history until a later approved retention policy is
implemented; payment occurrence/audit records remain durable. Monitor safe
worker counts and database growth without logging tokens, payloads, user names or
provider response bodies.

## Notification copy and privacy

Copy is versioned as `v1`. Private mode omits item names and amounts from both
title/body payloads. Detailed mode includes only the stored item name and
scheduled amount. English and Egyptian Arabic examples:

| Type | English | Egyptian Arabic |
|---|---|---|
| Upcoming | **A little heads-up! 👀** A payment is coming up in 3 days. Stay one step ahead! | **فاضل ٣ أيام على قسطك! 👀** دفعة جاية قرب ميعادها. دبّرها من بدري وخلي بالك مرتاح! |
| Due today | **Payment due today 👀** You have a payment due today. Take a look when you can. | **قسطك معاده النهارده! 👀** عندك دفعة مستحقة النهارده. دبّرها براحتك. |
| Overdue | **A quick payment reminder 👀** A payment is past due and isn't marked paid yet. | **تذكير سريع 👀** في دفعة فات ميعادها ولسه متسجلتش كمدفوعة. |
| User-confirmed paid | **Payment marked paid ✅** You marked this payment as paid. | **اتسجلت دفعتك ✅** تم تأكيد تسجيلك إن القسط اتدفع. |

The acknowledgement is generated only after the authenticated mark-paid request.
Undo does not claim that money moved; it only reverses the user's declaration.
Avoid guilt or pressure, and do not add fees, balances or bank states that Dabbarha
does not store.

## API contracts

Preferences use a complete `PUT` body, for example:

```json
{
  "reminders_enabled": true,
  "reminder_offsets": [7, 3, 1, 0],
  "reminder_time": "09:00",
  "timezone": "Africa/Cairo",
  "quiet_start": "22:00",
  "quiet_end": "07:00",
  "language": "ar",
  "privacy_mode": "private",
  "overdue_enabled": false,
  "categories": ["upcoming", "due_today", "payment_completed"]
}
```

Occurrence reads are bounded: `GET /obligations/{id}/payment-occurrences` accepts
`start_date` and `months` from 1–12 (default six months from the current month).
It idempotently materializes occurrences and returns each occurrence ID, due date,
amount, payment kind and unpaid/paid/superseded state. The user's paid/undo action
uses that occurrence ID and cannot address another user's records. A stale
superseded occurrence returns 409; unknown/foreign IDs return 404.

`GET /notifications?before_id=123&limit=50` returns newest-first history, a
`next_before_id` cursor and `unread_count`. `GET /notifications/unread-count`
returns the current count. `POST /notifications/{notification_id}/read` marks one
owned record read. The route identifier `obligation_detail` and nullable
`obligation_id` are data, not arbitrary URLs. The client must fetch the obligation
through the authenticated API before opening it.

All new routes use existing authentication, body limits, financial rate limits,
standard 422 validation, ownership and safe database-error responses. Existing
obligation, forecast, dashboard, affordability and authentication response
contracts/formulas remain unchanged.

## Operations and limitations

No production database migration, Expo credential, worker or provider account is
created by this code. Before activation, operators must review and apply the
additive migration, enable device-session auth, provision the new encryption key,
configure Expo project credentials on mobile, deploy one or more supervised
workers, and verify monitoring/rollback. Worker replicas may run concurrently.
Expo Push Service has no service-level availability guarantee; accepted push
messages may still not reach or display on the user's device. A provider timeout
or a crash at the send boundary can lose a message because the provider does not
offer an idempotent send key in this adapter.

## Verification

`scripts/run-phase-2d-verification.sh` requires the existing clean CPython 3.12
verification environment, Redis 7.4.11, PostgreSQL 18.6 and an existing
`pip-audit` executable. It installs or upgrades nothing, verifies the exact
dependency lock before running, performs dependency checks and the disposable
SQLite/PostgreSQL migration and concurrent-claim tests, then runs the complete
suite with real Redis/PostgreSQL tests mandatory. It streams output and saves a
complete log. Example (replace each tool path with the previously verified local
binary/environment path):

```sh
VERIFY_PYTHON=/path/to/clean-venv/bin/python \
REDIS_SERVER_BINARY=/path/to/redis-server \
POSTGRES_TEST_BIN=/path/to/postgresql/bin \
PIP_AUDIT_BIN=/path/to/audit-venv/bin/pip-audit \
bash scripts/run-phase-2d-verification.sh
```
