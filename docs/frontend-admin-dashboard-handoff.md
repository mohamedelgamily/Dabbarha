# Frontend handoff: administrator dashboard

This backend-only contract supports a later browser dashboard. Phase 2f.2 does
not add dashboard UI or modify the mobile client.

## Authentication flow

1. Authenticate with the existing durable v2 device-session flow. Legacy
   `/auth/login` tokens do not authorize administrator endpoints.
2. Send the current v2 access token and a six-digit TOTP code to
   `POST /admin/auth/step-up`.
3. Keep the returned short-lived admin `access_token` in memory only. It is
   session-bound and expires after five minutes by default. Refreshing the
   underlying device session does not refresh MFA; perform another TOTP step-up.
4. Call `GET /admin/auth/me` and the Phase 2f.2 operational endpoints with the
   step-up bearer token. A revoked session or role downgrade invalidates access.
5. On 401, end the local session or reauthenticate. On 403, require the approved
   admin role and a fresh MFA step-up. On 404, admin APIs may be disabled or the
   exact account may not exist. On 429, honor `Retry-After`. On 503, show a safe
   temporary service message and do not bypass MFA or rate limiting.

Do not place tokens in URLs, local storage, analytics, crash reports, or logs.
Never send passwords, TOTP codes, push tokens, notification bodies, or financial
values to browser telemetry. Follow the existing logout/revocation API and clear
the in-memory step-up token on logout, account switch, 401, and browser-session
termination.

## Dashboard integration

- Overview: `GET /admin/ops/overview?window_days=7`. Show that the refreshed-v2
  session metric is an activity indicator rather than a true active-user count.
  Render deletion metrics as unavailable when `deletions_available` is false;
  do not display null as zero. Label obligation totals as counts, never balances.
- System status: `GET /admin/ops/health`. Display component status and safe
  configuration readiness booleans only. A degraded status is useful diagnostic
  information; Redis outages may block the endpoint itself with 503, so maintain
  external monitoring too.
- Account lookup: `GET /admin/users/lookup` with exactly one exact account ID or
  normalized email. Do not add wildcard search or directory browsing. Display
  only returned account metadata and explain that the current backend has no
  suspension state.
- Session/device diagnostics: `GET /admin/users/{id}/sessions` with a bounded
  page. Show lifecycle metadata and platform only; never expect or request raw
  credentials or push tokens.
- Notification diagnostics: use global or user-scoped delivery endpoints with
  a bounded state filter and `next_cursor`. Show normalized error categories,
  attempts and timing, not private notification copy or raw provider errors.
  There is intentionally no manual retry action.

Operational admins and superadmins have the same Phase 2f.2 access. This phase
does not expose financial profiles, obligations, installment/payment amounts,
or mark-as-paid functions. It provides no impersonation or editing controls.
Phase 2f.3 temporary, audited, read-only support inspection remains pending;
do not build a financial-data inspection UI before that phase is approved and
implemented. The premium browser dashboard itself also remains pending.

## UX and security states

Use a separate administrator surface and make the current account role and MFA
expiry visible. Require step-up again after expiry instead of silently falling
back to normal-user credentials. Handle empty datasets, stale/unknown worker
heartbeats, inaccessible Redis, unavailable migrations, missing accounts,
validation errors, 429 `Retry-After`, and 503 states explicitly. Avoid bulk
exports and do not persist user lookup history in browser storage.
