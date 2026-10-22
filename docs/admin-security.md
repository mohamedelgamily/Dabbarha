# Administrator security foundation (Phase 2f.1)

Phase 2f.1 supplies administrator identity, TOTP step-up, offline provisioning,
revocation and security audit records. Phase 2f.2 adds operational APIs and
bounded account metadata. Phase 2f.3 adds temporary, audited, read-only financial
support grants as documented in `docs/admin-financial-support.md`. The browser
dashboard remains pending. Admin API routes return 404 while disabled.

## Roles and permissions

Every existing and new account has `admin_role=user`. `admin` and `superadmin`
are assigned only with the offline command. Phase 2f.1 has no public role-change
endpoint. `superadmin` does not itself authorize viewing anyone else's finances.
Financial support access requires a specific approved grant and a fresh TOTP
code for each read; operational admins cannot request or use those grants.

All admin APIs require a short-lived step-up access token issued by
`POST /admin/auth/step-up`. The caller first signs in using the existing v2 device
session flow, then supplies the six-digit authenticator code. The response has
`access_token`, `token_type`, `expires_in` and `admin_role`; it contains no refresh
token. Clients continue to hold the existing refresh token separately and must
perform a new TOTP step-up after refresh. The regular `/auth/login` and
`/auth/sessions` response contracts are unchanged.

The step-up token is HS256 and bound to the same durable v2 session (`sid`). Its
default lifetime is five minutes (configurable from one to fifteen). Revoking that
session invalidates it immediately. Admin access checks the current role in the
database on each request, so demotion also takes effect immediately. Admin
verification requires v2 sessions; legacy JWTs are rejected. Each valid TOTP
time-step can be used once, including under concurrent requests. Codes use the
standard 30-second, six-digit TOTP profile with a one-step clock-drift window.
Invalid attempts share the existing account/IP login-attempt limiter.

## Offline provisioning and revocation

Prepare the selected existing account through the normal registration flow. From
the backend root, explicitly verify `DATABASE_URL` points to the intended migrated
database, then supply the usual validated environment plus a dedicated,
random 32-byte base64 `ADMIN_TOTP_ENCRYPTION_KEY` through a trusted process
environment or secret manager, then run:

```sh
python -m app.commands.admin_access provision --user-id <EXISTING_USER_ID> --role superadmin
python -m app.commands.admin_access provision --user-id <EXISTING_USER_ID> --role admin
python -m app.commands.admin_access revoke --user-id <EXISTING_USER_ID>
```

The command asks for a typed confirmation. Provisioning prints a one-time
`otpauth://` URI and base32 seed to the operator's terminal; transfer it directly
to an authenticator app, keep it out of tickets and logs, and clear terminal
scrollback according to the operator procedure. The factor seed is stored in the
database only as AES-256-GCM authenticated ciphertext with user/key-id associated
data. The encryption key must be different from JWT, rate-limit and refresh-receipt
keys. Losing or replacing it makes enrolled factors unreadable. Retain the exact
key id with each encrypted factor; the application currently accepts only the
configured key ID, so rotation requires a separately reviewed re-enrollment or
re-encryption procedure before changing the key.

Offline role revocation clears the enrolled factor, revokes every durable session
for that user, and removes any encrypted refresh-recovery receipts in the same
transaction. It does not delete the user account. Provisioning and revocation are
audited with a null actor (the offline operator is not a web identity) and a
target account reference. The audit row's user references become null on account
deletion, avoiding retained identity links.

Do not set `ADMIN_API_ENABLED=true` until the additive migration is applied,
`SESSION_AUTH_ENABLED=true`, `SESSION_LEGACY_ISSUANCE=false`, the separate TOTP
encryption key is securely provisioned, and at least one superadmin has enrolled
an authenticator. The default is false. There is no development bypass.

## Audit and privacy

`admin_audit_events` records bounded action/outcome values, nullable actor/target
IDs, a one-way source fingerprint, and timestamp. It never stores OTP values,
JWTs, refresh tokens, passwords/hashes, TOTP seeds, raw IP addresses, email
addresses, free-form support notes, or financial data. Phase 2f.1 writes step-up
success/failure and offline role-provision/revocation events. Phase 2f.2/2f.3
add operational and grant-linked events; successful financial reads never put
financial values in audit rows.

The agreed 12-month retention period is a production configuration requirement,
not yet enforced by this phase. Production must configure retention and alerting
for failed MFA, role changes, and exceptional self-approved support grants. The
database's application role should not expose audit editing through APIs; a
production immutable archive/backup and retention policy still needs operational
and privacy/legal review. Deleting a user sets audit actor/target references to
NULL; it does not restore or retain the user's private records.

## Configuration

```dotenv
ADMIN_API_ENABLED=false
ADMIN_TOTP_ENCRYPTION_KEY=<separate-random-32-byte-base64-key>
ADMIN_TOTP_KEY_ID=v1
ADMIN_STEPUP_TOKEN_MINUTES=5
SESSION_AUTH_ENABLED=true
SESSION_LEGACY_ISSUANCE=false
```

The encryption-key placeholder is not valid key material. Use an explicit secret
manager for deployment; configuration reads process environment only. Admin API
enablement validates the session prerequisites at startup and fails closed.

## Dashboard contract for a later client

The future browser client can use `/admin/auth/step-up` and `/admin/auth/me` as
stable authentication endpoints. It must keep the step-up token in memory,
request a new TOTP step-up after its short expiry, and handle 401/403/404/503
without falling back to ordinary user privileges. Browser UI remains pending.
See `frontend-admin-dashboard-handoff.md` for the operational and support-access
contracts and their production requirements.
