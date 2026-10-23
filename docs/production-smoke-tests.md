# Production smoke-test checklist

Run the full suite in staging with synthetic accounts first. Production smoke
tests must be non-destructive and use an explicitly approved disposable test
account, never a real customer's account. Keep credentials in a secure test
runner; suppress response bodies, tokens and financial values in output.

## Before smoke tests

- Confirm the expected release SHA, migration revision, TLS certificate,
  private PostgreSQL and Redis connectivity, API/worker versions and secret
  scope without printing secret values.
- Confirm Swagger/OpenAPI are disabled, CORS is closed, trusted proxy peers are
  restricted, public port 6379 is unreachable, and no local SQLite database is
  being used by production.
- Confirm `/health` responds over HTTPS as liveness. Check `/ready` from the
  permitted infrastructure probe path: it should return only `ready` when
  PostgreSQL, Alembic revision and required Redis checks pass, and generic
  `unavailable` when any check fails. It must not expose component details.
  Exercise a protected route for end-to-end storage/auth behavior. Confirm
  alerts receive a safe synthetic event in staging before production.
- Confirm API and worker each have a separate service identity and expected
  runtime permissions. Confirm admin remains disabled unless all admin gates
  have separate approval.

## User and financial journey

Use unique synthetic email plus an environment-generated password. Print only
HTTP status and safe result booleans, not response JSON or credentials.

1. Register through `POST /auth/register`; verify expected 201. Duplicate
   registration should return the documented conflict without exposing the
   existing account.
2. Sign in through `POST /auth/sessions` when v2 sessions are enabled. Verify
   access/refresh response fields exist without displaying values. Check a
   protected `GET /auth/me`; verify an invalid bearer token returns 401.
3. Set and read a synthetic financial profile. Create an opted-in installment
   plan with a simple known schedule. Compare installment rows to the expected
   cent-exact schedule using a private assertion; never echo amounts in logs.
4. Read `/dashboard/summary`, `/forecast` and `/affordability`. Verify the same
   plan/payment is counted once and only in its scheduled month. Mark the
   current occurrence paid and verify projections exclude it; undo and verify
   the projection returns. Test cross-user IDs return 404.
5. Verify empty optional profile behavior and an account with no obligations.
   Do not assert that zero means “unknown”; the current API does not distinguish
   those states.
6. Confirm stale schedule updates return 409 and invalid/null values return 422
   without raw database or stack details.

## Sessions, rate limits and security

- Verify login, refresh, recovery within the bounded receipt period, logout,
  device-session revocation and password-confirmed account deletion in staging.
- Verify request rate limiting uses the shared Redis service across independent
  API processes. A protected route must fail safely with 503 if Redis is
  unavailable; production must never fall back to memory.
- Send a forged `X-Forwarded-For` through an untrusted path and verify the rate
  limiter sees the actual source. Verify the configured edge overwrites client
  forwarding headers and only its real peer is trusted.
- Verify response security headers, `Cache-Control: no-store` for private data,
  body-size/depth limits and safe 401/404/409/422/429/503 contracts.
- Ensure logs/traces contain no request bodies, authorization headers, tokens,
  email, push token or financial values.

## Notifications

In staging only, and only after session and push settings are intentionally
enabled:

- Register a disposable test device using the approved Expo development
  project; verify the raw token is never returned or logged.
- Verify the worker heartbeat advances, scheduled delivery is deduplicated, and
  mark-paid cancels pending reminders. Verify test-provider state does not claim
  OS/device delivery.
- Test provider outage, worker restart, retry limit, stale lease recovery,
  deleted/revoked device handling, privacy mode, English/Arabic copy and
  `Retry-After` behavior.
- Real iOS and Android delivery, permission prompts, deep links, lock-screen
  appearance and app-store receipt behavior require separate real-device tests;
  backend smoke tests do not prove them.

## Admin and deletion

Keep admin disabled for ordinary launch unless owner-approved admin controls are
actually operational. If enabled in staging, verify ordinary and legacy users
are denied, TOTP step-up is required, operational APIs redact private details,
and a financial support read requires a target-specific grant, fresh TOTP and
audit entry. Verify self-approval alerts. Do not inspect real customer records.

Delete the synthetic test account only after all other checks. Use fresh
password confirmation and explicit permanent-deletion confirmation. Verify 204,
old access/refresh credentials fail, and user-linked financial, session,
notification, token and conversation rows cascade. Confirm no subsequent
notification job is generated. Do not claim a provider-accepted push can be
recalled, and do not interpret this as backup deletion proof.

## Completion record

Record only release SHA, environment, timestamps, endpoint path, status code,
pass/fail boolean, sanitized request/correlation ID and operator. Do not include
email, token, amount, item name, raw response, secret, push token or database
URL. Attach staging evidence to release review. Production account deletion,
push delivery and store review require their separate owners and approvals.
