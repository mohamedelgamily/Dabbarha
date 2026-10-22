# Future administrator dashboard handoff

This is a backend contract and security handoff only. No browser or mobile
frontend is included in Phases 2f.1–2f.3.

Phase 2f.1 endpoints:

| Endpoint | Behavior |
|---|---|
| `POST /admin/auth/step-up` | Requires a live v2 device-session access token and six-digit TOTP. Returns a short-lived admin access token and role. |
| `GET /admin/auth/me` | Requires the unexpired step-up token. Returns only role and step-up expiry. |

The browser dashboard must use an authenticator app, retain the step-up bearer
token only in memory, and require a new MFA step-up after page reload/token expiry.
It must not place credentials in URLs, local storage, analytics, crash reports or
logs. Logout/revocation must use the existing session logout/revoke contract.

Future phase boundary:

- **2f.2 operational APIs:** aggregate metrics, system health, bounded account
  metadata search, and redacted notification operations. No financial detail.
- **2f.3 support inspection:** implemented as the exact endpoints in
  `admin-financial-support.md`: case-bound least-privilege scopes, 15-minute
  grants, per-read TOTP, read-only pagination, no export, and enhanced audit.
  Prefer another administrator's approval; exceptional self-approval is marked
  in the audit trail and requires production alert configuration.
- No admin API may edit financial records, mark payments paid, impersonate a user,
  recreate deleted records, or expose credentials, hashes, JWTs, refresh tokens,
  private keys or raw push tokens.

Later UIs must distinguish ordinary admin status from temporary financial-data
access; a `superadmin` role alone never grants the latter. Access must stop at the
grant expiry and be auditable per page/request. The agreed 12-month audit
retention and alert rules still require production configuration and privacy/legal
review before launch.
