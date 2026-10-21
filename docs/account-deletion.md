# Account deletion and privacy — Phase 2e

## Scope and rollout status

This document describes the backend implementation and a disclosure draft for
legal review. It does not claim that a public privacy policy or account-deletion
URL has been published, that production backups already enforce the approved
retention period, or that any external support-request service is operating.

The public bilingual information page is served at `/privacy/account-deletion`
by the backend. Before publishing that URL in a store listing, the operator must
deploy the backend publicly, configure the official store support contact, and
verify that encrypted backups expire within 30 days.

Google Play's current account-deletion requirement calls for a discoverable
external web resource where users can initiate deletion. This backend page is
currently informational and does not receive requests, so it is not by itself
an operational external deletion path or evidence of Play compliance. The
publisher must add and verify a real support/request channel before submitting
the URL in Play Console. See [Google Play's account deletion requirement](https://support.google.com/googleplay/android-developer/answer/13327111).

## Deletion policy

Deletion is immediate after a signed-in user submits the current password and
explicit permanent-deletion confirmation. A fresh password check is required in
addition to the access token; a stolen token alone cannot delete an account.
There is no grace period, recovery window, anonymized profile, or account-linked
deletion tombstone. A successful request removes the user row in one database
transaction. The foreign-key cascade removes the profile, obligations and
installment rows, sessions and refresh tokens, legacy access revocations,
notification preferences, encrypted device tokens, payment occurrences and
audit events, notifications and deliveries, and retained legacy conversations
and messages. The embedded financial profile and password hash disappear with
the user row. The global SQLite account-ID high-water mark is not account data
and contains no list of deleted IDs.

If the transaction fails, it is rolled back: the account remains active with all
its associated rows, and the endpoint returns a safe retryable error. A second
request made with the old access token receives 401 after deletion. The request
has no further effect; clients should clear local credentials after a successful
204 response.

The application does not retain a user-specific deletion record. HMAC rate-limit
buckets expire automatically with their configured windows. Operational logs
must not capture request bodies, authorization headers, passwords, push tokens,
financial payloads, or account identifiers. Operators should keep only short-lived
security metadata required for service operation and apply their separately
approved infrastructure log-retention policy.

Encrypted backups may contain data that was deleted after the backup was made.
The approved maximum backup age is 30 days; this is a deployment requirement,
not something the application can enforce. Do not describe it as operational
until backup configuration and expiry have been verified.

## Backup restoration and resurrection limitation

A snapshot-only restore from before a deletion can restore the deleted account
and its old session rows. No application behavior can discover that deletion
without a durable deletion ledger or post-backup change history. Phase 2e does
not add a user-linked ledger, so it cannot promise that every possible snapshot
restore will preserve subsequent deletions.

The privacy-preserving operational mitigation is to use encrypted PostgreSQL
base backups with continuous WAL archiving, keep the WAL stream at least as long
as the 30-day backup window, and restore to the latest available WAL position
rather than activating an old base snapshot by itself. Restore into an isolated
network first, verify that deletion transactions after the base backup have been
replayed, run ownership/orphan checks, and only then return the database to
service. If complete post-backup WAL is unavailable, do not activate that
snapshot as production. A separately stored, keyed-HMAC deletion journal could
support reconciliation when WAL is unavailable, but it is a user-linked
pseudonymous ledger and would require separate product/privacy approval; this
phase deliberately does not implement it.

The account-ID high-water mark prevents SQLite from reusing the greatest deleted
user ID for a newly registered account, which would otherwise let an unexpired
legacy JWT subject match the wrong person. It is a single global integer, not a
per-account deletion log. PostgreSQL's native sequence already avoids ID reuse.
Restoring an older SQLite backup can roll back that high-water mark as part of
the same snapshot; the restore quarantine/WAL rule still applies.

## Worker and token coordination

The notification worker and deletion endpoint take the same per-user database
row lock. Immediately before sending, the worker verifies that the user,
notification, device and session still exist and remain eligible; it retains the
user lock through the provider request and stores the result before releasing it.
The production Expo adapter has a five-second HTTP timeout. Database lock waits
are bounded; a timeout fails safely and can be retried. Deletion waits for a
request already in flight, then cascades the account. No new provider send can
begin after deletion commits. A notification accepted by Expo before deletion
completes may still arrive afterward; external push delivery cannot be recalled.

Legacy access tokens are checked against the user row and fail after it is
deleted. Version-2 access tokens also require their server-side session, which
cascades on deletion. Refresh tokens are stored only as hashes in rows that
cascade with the session; they cannot refresh after deletion. SQLite foreign
keys remain enabled by the application's connection setup.

## API contracts

### Authenticated in-app deletion

`DELETE /auth/account` requires a bearer access token and this JSON body:

```json
{
  "password": "<current-password>",
  "confirm_permanent_deletion": true
}
```

The password is verified against the existing Argon2id hash under the bounded
password-verification semaphore. The endpoint does not accept a user ID or email;
it only deletes the authenticated user's account. It returns 204 after the
transaction commits. Wrong passwords return 401, malformed/false confirmation
returns 422, and database/lock failures return a safe retryable 503 without
committing partial deletion. A stale token after success returns 401.

The public `GET /privacy/account-deletion` route returns the bilingual HTML
information page without login. It is informational only: there is no public
email-based deletion API, verification-code service, or support-ticket backend.
Users who cannot access the app must use the support contact configured by the
publisher on the official store listing. The operator must verify ownership
through the registered email or another reviewed method before manually
executing a deletion; support must never request the password. Do not publish an
unconfigured contact address or claim a request-handling service exists.

## English privacy/deletion disclosure draft (legal review required)

When you delete your Dabbarha account, we immediately and permanently delete
your profile and financial settings, obligations and installment schedules,
payment-status history, notification preferences and history, registered push
tokens, login sessions, and legacy conversation data. We ask for your password
and a final confirmation before deletion. Deletion cannot be undone. Encrypted
backups may contain data until they expire, no later than 30 days under the
approved retention policy. That retention limit must be verified in the
deployment before this disclosure is published. A push notification accepted
by its provider before deletion completes may still arrive. We do not verify
payments with banks.

If you cannot sign in, use the account-deletion contact published by the app's
publisher. We verify account ownership before processing the request and never
need your password. The publisher must configure and operate this external
request channel before representing it as available.

## مسودة إفصاح الخصوصية والحذف بالعربية (تحتاج مراجعة قانونية)

لما تحذف حسابك في دبّرها، هنحذف فورًا وبشكل نهائي بيانات ملفك الشخصي وإعداداتك
المالية، والالتزامات وجداول الأقساط، وسجل حالات الدفع، وإعدادات وسجل التنبيهات،
ورموز الإشعارات المسجلة، وجلسات تسجيل الدخول، والمحادثات القديمة. هنطلب كلمة
المرور وتأكيد نهائي قبل الحذف، والحذف ماينفعش التراجع عنه. ممكن بيانات تفضل في
نسخة احتياطية مشفّرة لحد انتهاء صلاحيتها، وبحد أقصى ٣٠ يومًا حسب سياسة الاحتفاظ
المعتمدة. لازم نتأكد من تطبيق المدة دي في بيئة التشغيل قبل نشر الإفصاح. لو مزود
الإشعارات قبل إرسال تنبيه قبل اكتمال الحذف، ممكن التنبيه يوصل بعد كده. إحنا مش
بنتحقق من المدفوعات عن طريق البنوك.

لو مش قادر تسجّل دخول، استخدم وسيلة التواصل المخصصة لطلبات الحذف والمنشورة من
ناشر التطبيق. هنتأكد إن الحساب يخصك قبل تنفيذ الطلب، ومش هنحتاج كلمة المرور.
لازم الناشر يجهّز وسيلة التواصل دي ويشغّلها قبل ما يعلن إنها متاحة.

## Deployment and legal review gates

- Configure encrypted backups and automatic expiry at or before 30 days; verify
  deletion from backup storage and document exceptions before publishing the
  retention claim.
- Enable PostgreSQL WAL archiving/recovery and rehearse restore quarantine and
  deletion replay. Do not restore snapshot-only backups directly to service.
- Publish the public information URL and an externally reachable support contact
  only after the support procedure and ownership checks are operational.
- Have counsel review the English and Arabic drafts, regional privacy/consumer
  requirements, backup language, and store policy before publication.
- No production migration or backup configuration is performed by this phase.
