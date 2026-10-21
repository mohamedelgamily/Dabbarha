# Frontend handoff — reminders and notifications

This guide is for Jomana's later Expo client work. Phase 2d changes only the
backend and documentation; no frontend source or package lock was edited.

## Current app integration points

The mobile app is under `mobile/`, uses Expo SDK 57, Expo Router and
`expo-secure-store`, and currently calls `/auth/login`. It does **not** currently
include `expo-notifications`. Push registration requires an active v2 device
session; use `/auth/sessions` for the mobile login flow and retain the returned
access/refresh credentials in SecureStore. Keep refresh rotation single-flight,
persist the retry key before sending, and clear all session credentials on logout.
Call `/auth/logout` with the refresh token (or bearer access token) and deactivate
the local notification registration when the user logs out.

Expo's push API requires a development build for remote notifications; Expo Go is
not a remote-push test environment for the current SDK. Add the matching
`expo-notifications` package with the Expo SDK-compatible installer in the
frontend repository, configure Android notification channels and APNs/FCM
credentials in EAS/project configuration, and use a real development/preview
build on each platform. Do not add that dependency in the backend repository.

Ask for operating-system permission only after the user has opted into reminders
or reaches the reminder settings. If permission is denied, keep reminder
preferences/history usable and explain how to re-enable notifications in system
settings; do not repeatedly prompt. Obtain an Expo push token using the app's
configured EAS project ID and register it with:

```http
POST /notifications/devices
Authorization: Bearer <v2-access-token>
Content-Type: application/json
```

```json
{"token":"ExpoPushToken[redacted-example]","platform":"ios"}
```

Store no push token in AsyncStorage or logs. The backend response intentionally
contains only an opaque device ID and platform. Call `PUT /notifications/devices/{id}`
after token rotation and `DELETE /notifications/devices/{id}` when the user turns
off push on that device. A revoked device session is rejected by the backend even
if the client fails to deactivate its token.

## Simple reminder settings flow

Use a short opt-in explanation such as “Get a heads-up before your payments are
due.” / «خد تنبيه قبل ميعاد قسطك». Keep the primary control obvious. Provide
accessible, translated controls for enabled state, reminder offsets, preferred
time, time zone, quiet hours, language, lock-screen privacy and optional overdue
reminders. Default presentation is private. Explain that detailed mode can show
the payment name and amount on the lock screen.

Labels:

| English | Egyptian Arabic |
|---|---|
| Reminders | التذكيرات |
| Reminder time | وقت التذكير |
| Time zone | المنطقة الزمنية |
| Quiet hours | وقت الهدوء |
| Keep details private | خلي التفاصيل خاصة |
| Show payment details | إظهار تفاصيل القسط |
| Remind me 7 days before | فكّرني قبلها بـ٧ أيام |
| Remind me 3 days before | فكّرني قبلها بـ٣ أيام |
| Remind me 1 day before | فكّرني قبلها بيوم |
| On the due date | يوم استحقاق القسط |
| Overdue reminders | تذكير بعد ميعاد القسط |

Use the notification's copy as-is where possible. Avoid duplicating the reminder
in a second local notification when the remote push already displays. Format Arabic
digits and RTL text consistently. English and Arabic notification templates and
privacy behavior are documented in `payment-reminders.md`.

## Payment status and undo

On an obligation detail, call `GET /obligations/{id}/payment-occurrences` for the
visible date range. Use the returned `id` for a specific occurrence; do not mark
an obligation or all monthly installments paid at once. A clear action is:

- **Mark as paid** / **تم الدفع**
- Confirmation feedback: **Payment marked paid** / **تم تسجيل دفع القسط**
- Undo action: **Undo payment** / **التراجع عن الدفع**

This is the user's declaration only. Do not call it a bank confirmation or
payment receipt. If the user undoes an accidental action, call the matching
`/undo-paid` endpoint; old reminder offsets are not resent automatically, though
future offsets that have not expired may still be scheduled.

## History, navigation and badges

Poll/refetch `GET /notifications/unread-count` when the app becomes active and
after mark-read actions; use `GET /notifications?before_id=...&limit=...` for
infinite-scroll history. Mark an item read with `POST /notifications/{id}/read`.
Use the supplied `route` identifier only as a routing hint. For
`obligation_detail`, fetch the nullable `obligation_id` through the authenticated
API and show the existing obligation detail modal. Current navigation is Expo
Router's `/(tabs)/obligations` screen; map the ID into that screen/modal rather
than trusting a URL or arbitrary notification payload. If the obligation was
deleted, show a safe unavailable state and return to the obligations list.

Keep OS badge count, app tab badge and unread count synchronized without treating
Expo ticket acceptance as proof that the user saw a notification. Handle loading,
empty, offline, 401/session expiry, 404 deleted obligation, 409 stale occurrence,
429/`Retry-After`, and 503 service-unavailable states. Keep local history cached
only as appropriate for the signed-in user and clear sensitive cached details on
logout.

## Real-device test checklist

Test iOS and Android development builds for permission accepted/denied, token
registration and rotation, v2 logout/revocation, foreground/background/killed
app behavior, Arabic RTL, private lock-screen copy, deep-link mapping, badge/read
state, network loss during refresh and notification taps. Use dedicated test
accounts and Expo's test tooling; never send test pushes to real users. The backend
test suite uses a mocked provider and disposable local infrastructure only.
