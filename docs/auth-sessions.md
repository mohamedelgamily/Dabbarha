# Phase 2b.6 — Authentication and durable device sessions

## Deployment gate

Session support is explicitly opt-in (`SESSION_AUTH_ENABLED=false` by default).
Legacy login works during rollout. Enable sessions only after reviewing/applying
revision `6b6a00000001`, provisioning the separate receipt key, upgrading/draining
all workers and completing SQLite/PostgreSQL verification. Missing tables or
storage failure return 503 rather than bypassing revocation. No migration runs
at application startup. PostgreSQL deployment and persistent migrations require
separate authorization; local SQLite remains the default.

When disabled, new session routes return 503 and legacy authentication does not
query the new tables. Disabling an already deployed session feature rejects v2
access tokens and disables server logout; it is not a transparent rollback.
Do not toggle it as an outage workaround. Never run mixed old/new workers while
promising session revocation: old workers lack the session checks.

## Passwords and compatibility

New registration accepts 8–128 Unicode code points, spaces and passphrases, with
no composition rule or trimming/normalization. Empty/all-whitespace and invalid
Unicode are rejected with 422. Existing Argon2id hashes and exact legacy password
values remain usable; login does not acquire the new registration length limits.
The existing mobile registration form must separately move from six to eight
characters and count Unicode code points consistently.

`POST /auth/login` retains its JSON email/password request and exactly
`access_token`/`token_type` response. Its default lifetime remains 60 minutes.
New clients explicitly use `POST /auth/sessions` with password authentication;
a legacy bearer alone is never upgraded to a long-lived refresh session.
Registration still returns 201 or duplicate-email 409: enumeration remains a
known compatibility risk. Generic login failures and dummy-hash protection stay.
No password recovery/change, MFA, admin role or public role assignment was added.
Future admin access needs server-controlled roles, explicit authorization,
audited privilege changes and stronger authentication; it is separate work.

## API contracts

All times in new API responses are **UTC Unix seconds**, represented by JSON
integers. SQLite/PostgreSQL also store UTC epoch BIGINT values, avoiding divergent
naive/timezone-aware datetime behavior. These are new response fields only.

| Endpoint | Contract |
| --- | --- |
| `POST /auth/sessions` | JSON email/password, optional trimmed `device_label` (1–80 Unicode code points when supplied); returns token pair |
| `POST /auth/refresh` | JSON `refresh_token` and `retry_key`, each canonical unpadded base64url encoding of 32 random bytes; returns original or rotated pair |
| `GET /auth/sessions` | v2 bearer required; own sessions only; `limit` 1–100 (default 50), `offset` 0–1,000,000; includes revoked/expired records until cleanup |
| `POST /auth/sessions/{uuid}/revoke` | v2 bearer and JSON password confirmation; owned session only; 204, repeated owned revocation safe; unknown/cross-user session 404 |
| `POST /auth/logout` | Exactly one of access bearer OR JSON `refresh_token`; 204 for completed/idempotent logout |

Illustrative token response (placeholders, not credentials):

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token": "<opaque 256-bit credential>",
  "refresh_expires_at": 0,
  "session_id": "<server-generated UUID>",
  "session_expires_at": 0
}
```

The zero timestamps above are placeholders, not valid configured expiration.
Session summaries contain `id`, `device_label`, `created_at`, `last_refreshed_at`,
`idle_expires_at`, `absolute_expires_at`, `revoked_at` and `current`. No raw tokens,
digests or receipt fields are exposed by session listing. A label is display text,
not hardware identity. Each password sign-in creates an independent session;
no silent device eviction or hard device cap was introduced.

New JWTs use existing HS256/key with `sub`, `sid`, unique `jti`, `iat`, `exp`,
`token_use=access`, `ver=2`. Any new-protocol marker requires the full valid claim
set. Refresh credentials are never access JWTs. Every protected v2 request checks
the authoritative session for user ownership, expiry and revocation. There is no
positive authorization cache in Redis. Next authorization observes revocation;
an already authorized financial request may finish.

Defaults: 15-minute access tokens; 30 days of refresh inactivity; 90-day absolute
session lifetime. Rotation extends idle expiry only up to absolute expiry.
Access expiry is clipped to both session deadlines. Reaching absolute/idle expiry
requires password sign-in. Existing JWT signing material is never rotated here.

## Bounded idempotent rotation

Before sending a refresh, the mobile client securely persists a **fresh 256-bit
retry key** with the current refresh token as one pending operation. The same old
token AND retry key are required for recovery; neither key alone nor a caller's
session ID selects credentials. Server lookup stores only SHA-256 hashes of these
values. Token entropy, not a slow password hash, protects opaque credentials.

Rotation consumes the current token and creates exactly one successor. The same
transaction stores an AES-256-GCM encrypted copy of the exact response with a
random 96-bit nonce and 128-bit authentication tag. Associated data binds the
receipt protocol version, session, token/generation, retry-key hash, successor,
recovery deadline and encryption key ID. No plaintext token is persisted. Receipt
encryption uses PyCryptodomex's authenticated API, not a custom cipher protocol.

The fixed recovery window is **60 seconds from the original rotation** and allows
**two recovery responses**, in addition to the original response. These approved
bounds are centralized in SessionSettings and intentionally not environment
settings that can silently expand a replay allowance.

| Request state | Result |
| --- | --- |
| Current, unused credential | Rotate once, commit, return pair |
| Consumed credential + matching retry key, before deadline, recovery budget available, successor still current/unused | Return exact original pair and increment recovery count atomically |
| Matching retry key but expired/exhausted recovery or successor advanced | 409 `refresh_recovery_unavailable`; no credentials or automatic revocation |
| Consumed credential + different retry key before original recovery deadline | 409 `refresh_conflict`; no credentials or revocation; deadline is unchanged |
| Consumed credential + different retry key at/after deadline, active family | Commit device-family revocation, then generic 401 |
| Unknown credential or expired/revoked family | Generic 401; no recovery |

Recovery does not mint a new access JWT, extend any expiration or move the window.
A consumed token whose own expiry passed can recover within its window only when
the session and successor remain active. Retry quota increments share the same
transaction and lock. A known late duplicate never gains credentials. Different
operation identities never create parallel descendants.

One device session equals **one entire token family**. Logout, device revocation
or suspicious reuse revokes all its refresh descendants and access JWTs. Other
devices remain valid. The server cannot distinguish a captured full request from
a genuine identical retry: an attacker holding both values can obtain the same
successor within the bound. Different-key conflict grace delays detection by at
most 60 seconds but returns no credentials. This is bounded recovery, not device
attestation or unconditional revoke-on-every-duplicate.

See [RFC 9700 §4.14](https://datatracker.ietf.org/doc/html/rfc9700#section-4.14) for
rotation/reuse principles. The specific receipt protocol is an application design.

## Transactions, outages and logout

PostgreSQL serializes lifecycle mutations on the session row using FOR UPDATE;
SQLite uses a short independent BEGIN IMMEDIATE transaction, bounded by a lock
waiting timeout. All workers share PostgreSQL, receipt key and Redis policy.
The service re-reads state after locking. Commit precedes success. Suspicious reuse
revocation commits before returning 401 so dependency rollback cannot undo it.
Ambiguous commit acknowledgements recover only with the same pending operation.

Database/receipt encryption failures return safe 503. Authentication SQL parameters
and exception details are suppressed. Redis remains the shared fail-closed limiter;
its outage does not disable quotas. 429 includes Retry-After. A quota/outage can
prevent recovery within the window; the fallback is sign-in, not indefinite grace.

Logout accepts an unexpired signed access token even if already revoked, to make
repetition safe. Expired access returns 401; use the refresh credential form.
Unknown/expired/revoked well-formed refresh logout returns indistinguishable 204;
known consumed refresh tokens can revoke their own family. Providing both forms
returns 422. Do not attach a stale bearer when using refresh-form logout.

Legacy logout stores a fingerprint of verified signing input and decoded signature;
protected legacy requests check it when sessions are enabled. Identical old JWTs
revoke together because the old format lacks per-device identity. Legacy acceptance
can only be retired after stopping issuance and waiting out the actual configured
maximum lifetime plus any applicable skew, under separately coordinated rollout.

## Configuration and maintenance

Use the existing explicit Uvicorn `--env-file` loading mechanism or process secret
injection. Never assume importing settings loads .env. Example templates contain
empty key fields only. SESSION_RECEIPT_KEY is standard base64 encoding of **32
securely random bytes**, distinct from JWT_SECRET_KEY and RATE_LIMIT_HMAC_KEY.
The application never generates a fallback key. Provision through secret management
or write directly to a protected local file; do not print/copy keys into logs.

| Variable | Default / constraint |
| --- | --- |
| SESSION_AUTH_ENABLED | false; explicit rollout gate |
| SESSION_RECEIPT_KEY | required when enabled; 32 random bytes encoded as base64 |
| SESSION_RECEIPT_KEY_ID | v1; 1–32 ASCII letters/digits/underscore/hyphen |
| SESSION_ACCESS_TOKEN_EXPIRE_MINUTES | 15; 1–60 |
| SESSION_REFRESH_IDLE_DAYS | 30; 1–90, no greater than absolute lifetime |
| SESSION_ABSOLUTE_DAYS | 90; 1–365 |
| SESSION_REFRESH_LIMIT | 10/session/minute; 1–100,000 |
| SESSION_REFRESH_IP_LIMIT | 60/IP/minute; 1–100,000 |
| SESSION_DB_LOCK_TIMEOUT_SECONDS | 5; 1–30 |
| SESSION_LEGACY_ISSUANCE / SESSION_LEGACY_ACCEPTANCE | true / true; coordinated cutover only |

New password sign-ins and device password confirmations share the existing login
IP and account/IP quotas and Argon2 semaphore. List/revoke share user read/write
quotas. Refresh and refresh-logout share IP/session buckets; account/session identity
is resolved server-side. Forwarding headers remain trusted only through configured
Uvicorn proxies. No identifier is stored directly in Redis keys.

After deployment approval, schedule `python -m app.commands.cleanup_sessions
--batch-size 500` at least once per minute using protected process configuration.
This maintenance command changes session data and must not be run against a real
database during this review. It clears expired encrypted receipts and deletes
families after absolute expiration in bounded batches. Successor consumption,
revocation and exhausted retry budget also clear recoverable ciphertext promptly.
Consumed token/retry-key hashes stay until absolute expiry for reuse classification.
No financial/user rows are cleaned up by this command.

Only one receipt key ID is supported initially. Changing the key makes outstanding
receipts unrecoverable (503), but does not change stored refresh hashes or JWTs.
A future key transition requires draining the 60-second receipt window and a
coordinated worker update; do not silently rotate it or reuse the JWT key. Backups
may retain encrypted receipts: restrict backup/key access. A database plus receipt-key
compromise exposes recoverable response data. Restoring stale session backups can
restore revoked state and requires a separate reconciliation/invalidation plan.

## Separate mobile handoff for Jomana

No frontend files were edited. Implementation must:

- Use `/auth/sessions` for password sign-in and keep access JWTs in memory.
- Store one versioned SecureStore record with refresh token/session/expiry and a
  pending retry key; persist pending state before sending. Never use AsyncStorage,
  URLs, query keys or diagnostic logs for credentials.
- Use one refresh coordinator across callers. Retry the SAME pending operation,
  with bounded backoff/jitter; never invent a new key after an ambiguous send.
- Persist the successor before releasing waiting API calls. After a crash, retry
  saved pending state only within server recovery bounds. If lost response/storage
  failure exceeds them, require sign-in. SecureStore is not a multi-key transaction.
- On 409, first join another caller or reload a successfully saved successor. If
  recovery is unavailable, stop retrying and require controlled reauthentication.
- Preserve credentials on ordinary network/429/503 errors; do not treat every
  `/auth/me` failure as invalid credentials. An extended refresh outage can still
  make pending recovery impossible.
- Guard late responses with an auth generation. Logout/account changes must stop
  refresh work, revoke the server session, clear credentials and cancel/clear all
  user financial caches. Scope query keys to the current user.
- Distinguish local credential deletion from confirmed server revocation when offline.
  Do not blindly retry financial mutations after ambiguous network failures.
- Verify native storage options on installed Expo SDK 57. Android backup must not
  restore encrypted credentials; iOS keychain values can survive reinstall. Do not
  silently enable biometric restrictions that can invalidate stored credentials.

See [Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/) and
[PyCryptodome authenticated modes](https://www.pycryptodome.org/src/cipher/modern).

## Verification and remaining work

Tests create their own disposable SQLite files and PostgreSQL cluster/databases;
no test accepts a production database URL. POSTGRES_TEST_BIN names installed server
binaries only; REQUIRE_POSTGRES_TESTS=1 fails if absent. The cluster uses a private
Unix socket, no TCP listener, and is removed after tests. Keep real Redis tests
required with REQUIRE_REDIS_TESTS=1 and REDIS_SERVER_BINARY.

Local verification passed against disposable SQLite, PostgreSQL and Redis services
on macOS. Production launch still requires approval and execution of the additive
migration on the deployment database, separate receipt-key provisioning, target
Linux execution, frontend implementation/native testing and legacy retirement
planning. The eight-character password minimum and duplicate-registration 409 are
conscious product decisions; zero advisory hits alone do not establish production
readiness.
