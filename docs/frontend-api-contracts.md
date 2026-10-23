# Mobile API Contracts — Dabbarha v1

Source of truth: current FastAPI routes and Pydantic schemas in `app/api/routes/` and `app/schemas/`. Paths below are rooted at the backend origin. Examples use placeholders only. Except for `/health` and the public deletion-information page, routes require `Authorization: Bearer <access_token>`. Do not log credentials or private payloads. Money is JSON decimal text with two fractional digits; dates are ISO `YYYY-MM-DD`; timestamps are ISO 8601; session epoch fields are Unix seconds.

## Public service status

`GET /health` returns `{ "status": "ok" }`. It is a simple process liveness check, not a guarantee that database, Redis, worker or notification dependencies are healthy. Do not use it as the sole production readiness monitor.

## Authentication and account

### `POST /auth/register` — public, 201

Required JSON: `name` (trimmed nonblank, max 120), `email` (valid email), `password` (8–128 Unicode code points, nonblank content; spaces allowed; no normalization). Extra fields are rejected. Financial values are not accepted during registration.

Response: `{ "id": 123, "name": "Nour", "email": "nour@example.com", "monthly_income": "0.00", "fixed_expenses": "0.00", "currency": "EGP", "created_at": "<ISO timestamp>" }`.

### `POST /auth/login` — public legacy flow, 200

Required: `email`, `password`. Response preserves `{ "access_token": "<JWT>", "token_type": "bearer" }`. It has no refresh token. If legacy issuance is disabled, the response is 410 and the client must upgrade/use device sessions. The default legacy token duration is 60 minutes unless configured otherwise.

### `POST /auth/sessions` — public v2 sign-in, 200

Required: `email`, `password`; optional `device_label` (trimmed, 1–80). Response: `{ "access_token": "<JWT>", "token_type": "bearer", "expires_in": 900, "refresh_token": "<opaque>", "refresh_expires_at": 0, "session_id": "<UUID>", "session_expires_at": 0 }`. New access tokens normally expire after 15 minutes; refresh inactivity expires after 30 days and absolute session lifetime after 90 days. Actual expiry values in the response are authoritative.

Store access/refresh tokens and the random retry key only in platform secure storage. Never use AsyncStorage, logs, analytics, URLs or crash breadcrumbs. Serialize refresh requests globally. Persist one canonical random 32-byte base64url `retry_key` before first refresh request; on an ambiguous network result retry the same old refresh token with that same key. The server's encrypted response receipt allows at most two retries during 60 seconds and returns the exact same pair without extending expiry. A different retry key cannot recover that response. A 401 requires sign-in; a 409 means refresh conflict/recovery is unavailable and also requires sign-in; 429 requires honoring `Retry-After`; 503 is retryable only with the same persisted request values during the receipt window.

### `POST /auth/refresh` — public credential exchange, 200

Required: `{ "refresh_token": "<opaque>", "retry_key": "<same persisted random key>" }`. Both values must be canonical 32-byte base64url strings. Response is the same `SessionToken` structure as session sign-in.

### `GET /auth/sessions` — v2 authenticated

Optional pagination: `offset` 0–1,000,000 (default 0), `limit` 1–100 (default 50). Returns an array of `{ id, device_label, created_at, last_refreshed_at, idle_expires_at, absolute_expires_at, revoked_at, current }`. Times are epoch seconds. A device is a server-side session, not a validated hardware identity.

### `POST /auth/sessions/{sid}/revoke` — v2 authenticated, password confirmation, 204

Body `{ "password": "<current password>" }`. Revokes that owned device session and its refresh family. Wrong-account IDs return a safe not-found result; wrong password returns 401.

### `POST /auth/logout` — v2 feature must be enabled, 204

Provide exactly one credential: either `Authorization: Bearer <access-token>` or JSON `{ "refresh_token": "<opaque>" }`. Do not send both. Clear local secure storage and sensitive user caches after success; if offline, clear local credentials immediately and retry server revocation when possible.

### `GET /auth/me` and `PATCH /auth/me`

Returns `{ id, name, email, monthly_income, fixed_expenses, currency, created_at }`. PATCH accepts any subset of `monthly_income`, `fixed_expenses` (finite nonnegative supported money, up to two decimal places) and `currency` (trimmed, uppercased, 1–3 characters). Explicit null and extra fields are rejected. Identity/password changes are not supported here.

### `DELETE /auth/account` — authenticated, fresh password, 204

Body `{ "password": "<current password>", "confirm_permanent_deletion": true }`. Deletion is immediate after transaction commit and irreversible. It removes linked financial records, payment/audit history, notification preferences/history/tokens, sessions and legacy conversation data. The request must be confirmed in-app after an explicit warning; clear local secure storage on success. Old access and refresh credentials stop working. `GET /privacy/account-deletion` is public bilingual information only; it does not submit or process external deletion requests. Configure a real external support channel before claiming one exists.

## Obligations and installment plans

All monetary values below use the shared Numeric(12,2) range/precision validation. Text is trimmed Unicode with field-specific maxima. Installment and forecast durations are bounded by schema rules and supported calendar arithmetic; validation failures return 422.

### `POST /obligations` — legacy obligation, 201

Required fields: `provider`, `item_name`, `category`, `total_amount`, `monthly_installment_amount`, `start_date`, `term_months`, `due_day_of_month`. Optional `status` (active/completed/late/defaulted, default active), `source` (manual_entry/chatbot_entry, default manual_entry). This creates a legacy record; it is not automatically interpreted as a financed purchase plan.

### `GET /obligations`, `GET /obligations/{id}`

List or fetch only the caller's obligations. Response includes ID/user ID, provider/item/category, legacy and plan fields, exact date/term/status/source, schedule version and created/updated timestamps. Cross-user and missing IDs return 404.

### `PUT /obligations/{id}` — partial legacy update

Accepts only supplied legacy fields from create (all explicit nulls are rejected); final merged state is validated. For a plan, schedule-calculation fields cannot be edited through this route. Use the versioned plan endpoint instead.

### `DELETE /obligations/{id}` — authenticated, 204

Deletes only the caller's obligation and cascaded schedule/payment/reminder data.

### `POST /obligations/installment-plans` — opt-in plan, 201

Required: `provider`, `item_name`, `category`, `purchase_price`, `payment_method` (`manual` or `automatic`), `start_date`, `term_months`, `due_day_of_month`. Optional: `interest_method` (`none`, `flat`, `reducing_balance`; default none), `nominal_annual_interest_rate` (0–100%, at most four fractional digits; this is nominal, not APR), `monthly_installment_amount` (required for manual, forbidden for automatic), `down_payment_amount` (default 0), `down_payment_date`, `down_payment_paid` (default false), `status`. Positive down payments require an exact date and must be less than purchase price. A paid down payment requires a date. Manual monthly amounts remain provider-entered; disclosed interest does not change them.

Automatic plans persist their exact installment rows. The final row absorbs deterministic cent rounding/payoff adjustment. `purchase_price` is the calculation input; `total_amount` mirrors it for backward compatibility. Legacy records are unchanged unless explicitly converted.

### `PUT /obligations/{id}/installment-plan`

Requires the complete plan shape plus current `schedule_version`. The server uses optimistic version checking; stale versions return 409. Do not directly change a down-payment paid state—use its payment occurrence. Existing plan calculations and full request rules apply.

### `POST /obligations/{id}/convert-to-installment-plan`

Requires the complete plan shape plus `confirm_conversion: true`. This is explicit conversion after review; legacy records are not silently recalculated. Already converted/changed records return 409.

### `GET /obligations/{id}/installments`

Returns `{ obligation_id, schedule_version, installments: [{ installment_number, due_date, scheduled_amount, principal_amount, interest_amount }] }`. The saved schedule is authoritative for plan display and projection. Legacy obligations return 404 for this exact schedule resource.

### Payment statuses

`GET /obligations/{id}/payment-occurrences?start_date=YYYY-MM-DD&months=1..12` returns `{ "rows": [...] }`. Optional `start_date` defaults to the server's current calendar date. Occurrence shape: `{ id, obligation_id, installment_id, occurrence_key, payment_kind, due_date, scheduled_amount, schedule_version, state, paid_at }`; state is unpaid/paid/superseded. Dates are clamped for legacy monthly schedules and exact for saved plans. The route materializes expected rows idempotently. Payment-occurrence routes require notification/payment tracking configuration; if disabled they return 503.

`POST /obligations/{id}/payment-occurrences/{occurrence_id}/mark-paid` records the user's declaration for one occurrence. `POST .../{occurrence_id}/undo-paid` reverses an accidental declaration. Both return the occurrence shape. Superseded schedule rows return 409; ownership mismatch returns 404. Marked-paid regular rows are excluded from projected remaining monthly totals; undo restores them. Neither operation verifies a bank transaction.

## Dashboard, forecast and affordability

### `GET /dashboard/summary`

No query parameters are accepted. Representative response:

```json
{
  "monthly_income": "6000.00", "fixed_expenses": "1000.00",
  "current_month_obligation_payments": "100.00",
  "current_month_installment_payments": "100.00",
  "current_month_down_payment_payments": "0.00",
  "current_month_overdue_down_payment_payments": "0.00",
  "current_month_down_payment_details": [],
  "current_month_projected_buffer": "4900.00",
  "has_current_month_negative_buffer": false, "active_obligations_count": 1
}
```

Response includes `monthly_income`, `fixed_expenses`, `current_month_obligation_payments`, `current_month_installment_payments`, `current_month_down_payment_payments`, `current_month_overdue_down_payment_payments`, `current_month_down_payment_details`, `current_month_projected_buffer`, `has_current_month_negative_buffer`, and `active_obligations_count`. Paid occurrences already recorded are excluded from projected remaining payments for the relevant month.

### `GET /forecast?start_month=YYYY-MM-DD&months=1..60`

Returns, for example:

```json
{ "rows": [{
  "month": "2026-10-01", "income": "6000.00", "fixed_expenses": "1000.00",
  "obligation_payments": "100.00", "installment_payments": "100.00",
  "down_payment_payments": "0.00", "overdue_down_payment_payments": "0.00",
  "down_payment_details": [], "projected_buffer": "4900.00",
  "has_negative_buffer": false
}] }
```

Returns `{ "rows": [...] }`, each row containing month start, income, fixed expenses, obligation/installment/down-payment totals, overdue down-payment details, projected buffer and negative-buffer flag. `start_month` may be any valid date; returned row dates are month starts. Paid occurrences inside the requested window are not projected again. An unpaid overdue down payment appears once in the first month, with its original date and overdue flag. Invalid/extreme calendar windows return 422.

### `POST /affordability`

Legacy mode requires `amount`, `start_date`, `term_months` and evaluates that recurring monthly commitment. Plan mode requires `purchase_price`, `payment_method`, `start_date`, `term_months`, with manual/automatic and down-payment/rate fields following installment-plan rules. Response: `{ classification, worst_projected_buffer, worst_buffer_percentage, worst_month, explanation, monthly_results: [{ month, income, fixed_expenses, existing_obligation_payments, proposed_commitment_amount, proposed_installment_amount, proposed_down_payment_amount, projected_buffer }] }`. Existing paid occurrences are not double-counted in projected existing payments. The evaluator covers the full commitment period (maximum 1,200 months) and does not change the established formulas for legacy records.

## Notifications and payment reminders

Notification endpoints require v2 sessions when push-device registration is involved. All notification endpoints return 503 when notification configuration is disabled/unavailable. Register push permission only after user opt-in. Never store or log raw Expo push tokens on the client; server responses expose device ID/platform/state, not the token.

- `GET /notifications/preferences`: returns full preferences; may lazily create defaults. Example: `{ "reminders_enabled": false, "reminder_offsets": [7,3,1,0], "reminder_time": "09:00", "timezone": "Africa/Cairo", "quiet_start": "22:00", "quiet_end": "07:00", "language": "en", "privacy_mode": "private", "overdue_enabled": false, "categories": ["upcoming","due_today"], "updated_at": "<ISO timestamp>" }`.
- `PUT /notifications/preferences`: full replacement of settings: `reminders_enabled`, `reminder_offsets` from 7/3/1/0 with unique entries, `reminder_time` HH:MM, IANA `timezone`, both `quiet_start`/`quiet_end` or both null, language `en`/`ar`, privacy `detailed`/`private`, `overdue_enabled`, and unique allowed `categories` (`upcoming`, `due_today`, `overdue`, `payment_completed`).
- `POST /notifications/devices`: body `{ token: "ExpoPushToken[<token>]", platform: "ios"|"android" }`; returns opaque device metadata.
- `GET /notifications/devices`: lists current user's device metadata.
- `PUT /notifications/devices/{device_id}`: register rotated token/platform; owned device only.
- `DELETE /notifications/devices/{device_id}`: deactivate owned device, 204.
- `GET /notifications?before_id=<id>&limit=1..100`: descending history; response `{ items, next_before_id, unread_count }`. Each item carries `id`, nullable `obligation_id`, `notification_type`, `title`, `body`, nullable `route`, ISO `scheduled_at`, `delivery_state`, nullable `read_at`, and ISO `created_at`.
- `GET /notifications/unread-count`: `{ unread_count }`.
- `POST /notifications/{notification_id}/read`: marks the owned item read and returns its notification.

Notification fields include ID, nullable obligation ID, type, title/body, nullable route, scheduled time, delivery state, read time and created time. Deep-link only using the allowlisted route identifier (`obligation_detail`) and fetch the obligation again through the authenticated API. A deleted/missing target must show a safe unavailable state. Provider acceptance does not prove OS display or user receipt. No real-device push delivery has been verified.

## Common errors and recovery

Errors normally use `{ "detail": "..." }`; request validation uses `{ "detail": [{ "type", "loc", "msg" }] }` and deliberately excludes submitted input values.

- 401: credentials expired/invalid/revoked or password confirmation failed. Clear session state when revoked; for access expiry, attempt one serialized v2 refresh if available, then sign in again.
- 404: resource missing/not owned or disabled admin surface. Do not disclose another user's existence.
- 409: stale plan/payment state, rotation conflict or duplicate registration. Refetch the affected resource; refresh conflict requires reauthentication.
- 410: legacy token issuance disabled; upgrade to v2 device sessions.
- 422: invalid field/query/business shape. Show field errors without echoing secrets.
- 429: rate limited; obey integer `Retry-After`, avoid tight retries.
- 503: security/session/notification/storage dependency unavailable. Show recoverable unavailable state, honor `Retry-After`, never silently bypass security.

Sensitive/authenticated responses use no-store security headers. Don't build a client-side retry loop for permanent 401/409/422 responses.

## Not mobile APIs / pending functionality

`/admin/*` is the separate browser-admin backend surface and must not be included in ordinary user navigation. The browser dashboard remains future work. The public `/privacy/account-deletion` route is disclosure only; an external deletion-request channel must be deployed separately. Backend-local tests do not verify production hosting, App Store/Google Play review, real push delivery, or real-device behavior.
