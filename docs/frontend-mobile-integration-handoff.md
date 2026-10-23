# Mobile Integration Handoff for Jomana

This is a backend contract and UX handoff; it does not modify or claim implementation of the Expo frontend. Use `docs/frontend-api-contracts.md` as the endpoint/schema reference. This consolidated guide supersedes older phase-specific suggestions when they conflict with current schemas.

## Product and visual system

Keep Dabbarha's calm, trustworthy personal-finance visual language consistent across Home, Obligations, Forecast and Profile. Show amounts with the user's currency, two decimal places and clear Egyptian localization. Distinguish committed monthly totals, paid installments, remaining projections and overdue down payments. Never imply bank synchronization or verified transfers; “paid” means the user marked it paid.

## Localization, RTL and accessibility

Provide English and natural Egyptian Arabic for every label, validation message, empty state, alert, offline/retry state, confirmation and notification setting. Persist language preference on the device/account as product design specifies, initialize Arabic screens with RTL, and mirror directional icons/spacing without mirroring currency symbols incorrectly. Support screen readers, dynamic text, semantic controls, clear focus order, contrast, touch targets and non-color status indicators. Preserve language selection across app restart and logout according to the privacy policy; do not attach language preference to a deleted account.

Suggested copy:

| English | Egyptian Arabic |
|---|---|
| Monthly income | دخلك الشهري |
| Fixed expenses | مصاريفك الثابتة |
| Purchase price | سعر الشراء |
| Down payment | المقدم |
| Monthly installment | القسط الشهري |
| Provider payment | القسط اللي الجهة محدداه |
| Mark as paid | تم الدفع |
| Undo payment | التراجع عن الدفع |
| Upcoming payment | دفعة جاية |
| Payment completed | تم دفع القسط |
| Keep details private | خلي التفاصيل خاصة |
| Delete account | حذف الحساب |

Show a short explanation that disclosed nominal interest is not APR and excludes fees that the user did not enter. For manual payment entry, the entered provider amount is authoritative and must never be silently replaced by an estimate.

## Authentication and session lifecycle

Use `POST /auth/sessions` for the mobile sign-in flow. Save access token, refresh token, retry key and session metadata in Expo SecureStore (or equivalent OS-backed secure storage); do not use AsyncStorage for credentials. Implement one shared refresh promise so simultaneous 401s cannot rotate the same credential independently. Persist the retry key before sending `/auth/refresh`, then atomically save the returned token pair. Retry one failed original request only after a successful refresh. Honor the documented 60-second/two-retry response-recovery limit. On logout, revoke using `/auth/logout`, clear credentials and per-user private caches; if offline, clear locally first and report that server revocation will retry. Device revocation, password confirmation, inactivity expiry, absolute expiry, account deletion and password change should lead to a safe reauthentication flow.

Legacy `/auth/login` has no refresh token and exists for compatibility; use it only while the client rollout has not enabled durable device sessions. An HTTP 410 means update the app. Never present admin TOTP or admin routes in the ordinary mobile experience.

## Onboarding, profiles and financial plans

Registration captures name/email/password; it does not accept income or expenses. After sign-in, offer optional profile setup through `PATCH /auth/me`. Preserve zero/unknown distinctions in UI because the current model defaults unset income/expenses to zero and cannot distinguish “not set” from “user entered 0.” This is a product/data-model limitation, not a reason to invent a frontend-only backend field.

For plans, first ask whether the user already knows the provider's monthly payment. If yes, use manual mode and preserve that exact recurring amount. Otherwise, offer automatic no-interest/flat/reducing-balance options; reveal rate inputs only when an interest method needs them. Explain the nominal annual rate, show the backend's persisted exact schedule and final-installment adjustment, and require review before legacy conversion. A down payment needs an exact date; distinguish paid from unpaid; paid amounts are not projected. A paid regular occurrence reduces projected remaining totals for its due month; undo restores it without automatically resending expired reminders. Use `schedule_version` for plan updates and refetch on 409.

## Dashboard, forecast and affordability

Use `GET /dashboard/summary` for the current-month overview; use `GET /forecast` for the selected period. Render the backend's totals and row-level down-payment details directly. Do not recompute interest, round schedules independently, or sum legacy `total_amount` to infer future monthly costs. Use `/obligations/{id}/installments` for an opted-in plan's exact schedule. Affordability is a complete-period assessment; display the returned classification, worst month/buffer, explanation, and month rows. Clearly distinguish current projected amounts from a guarantee or financial advice.

## Payment status and notifications

Fetch the appropriate `payment-occurrences` window and act on one occurrence ID. Show a clear confirm/undo flow, event feedback, loading lock and failure recovery. A 409 stale/superseded occurrence requires refetch. Avoid duplicate local alerts when a remote notification will display.

Ask for OS push permission only after opt-in. Register an Expo push token after v2 sign-in, rotate using `PUT /notifications/devices/{id}`, deactivate on opt-out/device logout, and never log or persist the raw token in app storage. Add `expo-notifications` only in the frontend repo with the Expo SDK-compatible version. Configure EAS project ID, APNs/FCM and Android channels in the frontend deployment. Notification settings include time zone, quiet hours, reminder offsets, language, categories and lock-screen privacy. Use the backend-supplied `route` only as an allowlisted navigation hint; fetch current obligation data before displaying detail. Handle OS permission denial gracefully. No real push delivery or device behavior is verified by backend tests.

## Loading, errors, offline and recovery

Provide consistent loading/skeleton, empty, offline/stale, retry and destructive-confirmation states. Honor `Retry-After` on 429/503; do not tight-loop. 401 permits one serialized refresh attempt, then sign-in. A 409 requires refreshing the conflicting plan/payment/session state. 410 instructs upgrade. 422 maps safe field errors to the form. On 404 show a non-disclosing unavailable state. Never surface raw SQL/provider errors or show stale financial data as current after account switch/deletion.

## Account deletion

Place Delete Account in Profile/Settings with clear permanent-loss copy, password confirmation, a separate final confirmation and success/failure feedback. Provide full English/Arabic and RTL, no dark patterns. After 204 clear SecureStore, query cache, local account-specific data, push registration and navigation state. Do not claim a backup is erased immediately: the approved encrypted-backup retention window is up to 30 days and its production enforcement remains unverified. The public information page is not an external request form; deployment must configure a real verified request channel.

## Required client acceptance

Test on supported iOS and Android devices/builds: onboarding, Arabic RTL, language persistence, passphrases, refresh races/network loss, session/device revocation, calculation schedule display, down-payment paid/overdue states, mark/undo paid, forecast totals, affordability, notification permission/preferences/token rotation/deep-link/read/badges, offline recovery, account deletion and cache clearing. Run frontend type checks/localization/accessibility tests. The mobile project and its package files remain untouched in this backend phase.

The browser admin dashboard is a separate future workstream and must use the admin API only behind its independent MFA/grant controls.
