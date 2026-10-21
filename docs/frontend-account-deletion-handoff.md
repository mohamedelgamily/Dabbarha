# Frontend handoff — Account deletion

For Jomana's later Expo client work. Phase 2e changes the backend and documents
only; no mobile source or package lock is modified.

## Profile / Settings flow

Add **Delete Account** / **حذف الحساب** in Profile or Settings. Use two clear
steps: first explain that deletion is permanent and list the profile, financial
settings, obligations/installments, payment history, reminders/devices, sessions,
and conversation history that will be removed; then show a final confirmation
with a current-password field and an explicit destructive action. Do not hide,
delay, shame, or repeatedly dissuade the user. Keep the regular cancel/back action
equally easy to find.

English copy:

- Title: **Delete your account?**
- Explanation: **This permanently deletes your profile and all Dabbarha data,
  including your plans, payment history, reminders, devices, sessions, and old
  conversations. You can't undo this.**
- Password label: **Current password**
- Final action: **Permanently delete account**
- Cancel: **Keep my account**
- Success: **Your account and data have been deleted.**
- Wrong password: **That password didn't match. Try again.**
- Temporary failure: **We couldn't finish deletion. Your account is still active;
  please try again.**

Egyptian Arabic copy:

- العنوان: **تحب تحذف حسابك؟**
- التوضيح: **الحذف نهائي وهيشيل ملفك وكل بياناتك في دبّرها، ومنها خططك وسجل
  الدفع والتنبيهات والأجهزة والجلسات والمحادثات القديمة. مش هتقدر ترجعها.**
- كلمة المرور: **كلمة المرور الحالية**
- التأكيد النهائي: **حذف الحساب نهائيًا**
- الإلغاء: **خلّي حسابي**
- النجاح: **تم حذف حسابك وبياناتك.**
- كلمة مرور خاطئة: **كلمة المرور مش مطابقة. جرّب تاني.**
- عطل مؤقت: **ماقدرناش نكمل الحذف. حسابك لسه موجود؛ حاول تاني.**

Implement full English/Arabic translations, natural RTL layout, accessible focus
and screen-reader labels, and a visible loading state. Do not put the password in
analytics, crash reports, logs, persisted state, or AsyncStorage.

## API and local session cleanup

Send the active bearer token with:

```http
DELETE /auth/account
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "password": "<current-password>",
  "confirm_permanent_deletion": true
}
```

On HTTP 204, clear all access token, refresh token, retry/idempotency key, device
session metadata, push-registration identifiers, cached profile/financial data,
notification history and user-scoped query caches from Expo SecureStore and
other local storage. Do not call logout after a successful delete; server-side
sessions and registered push tokens were already removed atomically. Navigate to
the signed-out welcome screen and show the translated success message.

Handle 401 wrong-password separately from 422 validation, 429 `Retry-After`, and
503 temporary storage/lock failures. On a network timeout, deletion may have
committed while its response was lost. Retry with the old token; if it returns
401, clear local credentials and explain that the account may already be gone.
Never silently represent an ambiguous result as confirmed until the client has
resolved it. If a notification was accepted by Expo before the delete response,
it may still arrive afterward.

The public bilingual information page is `/privacy/account-deletion`. Link it
from the app's help/privacy area once the backend URL is deployed and the
publisher has configured the official support contact. For users unable to sign
in, describe the external identity-verification path; never ask them to send a
password. The API does not currently accept public email-based deletion requests.

No user data export, account recovery, backup restore, or re-registration with
the same historical database ID should be added in the frontend flow.
