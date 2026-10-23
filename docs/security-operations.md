# Security operations

Status: operating procedure proposal. No production secrets or access policies
were created or changed.

## Secret inventory and access

Maintain a secret inventory with owner, environment, service scope, creation
date, rotation trigger, recovery procedure and last verification. Record secret
identifiers and status only; never put values in Git, tickets, logs, screenshots
or this inventory.

| Secret/configuration | Used by | Required operational treatment |
|---|---|---|
| `JWT_SECRET_KEY` | API; currently required by common settings import in worker | Unique random high-entropy value. A change invalidates old signed access tokens. Use a coordinated, approved rotation and user/session recovery plan. Resolve the worker's unnecessary dependency before giving it this API key. |
| `RATE_LIMIT_HMAC_KEY` | API processes | Separate random value, identical across all API workers in one environment. A change changes opaque limiter bucket identities and effectively resets existing quota history. |
| `SESSION_RECEIPT_KEY` | API processes when sessions enabled | Separate 32-byte base64 key shared by API instances. The application has one active key ID; rotation can make in-window encrypted retry receipts unreadable and require sign-in for affected requests. |
| `PUSH_TOKEN_ENCRYPTION_KEY` | API and worker when notifications enabled | Separate 32-byte base64 key, identical wherever ciphertext is read. Current code supports one active key; rotation requires a reviewed decrypt/re-encrypt operation. Do not enable push until tested. |
| `ADMIN_TOTP_ENCRYPTION_KEY` | API when admin is enabled | Dedicated 32-byte base64 key. Losing it can make enrolled TOTP factors unavailable. Recovery/re-enrollment requires controlled operator access and audit. Keep admin disabled until the recovery path is rehearsed. |
| PostgreSQL credentials/CA | API, worker, migration job | Separate migration owner and runtime roles. Use TLS with CA and hostname verification. Rotate each role independently and confirm pool reconnection. |
| Redis credential/endpoint | API instances | Shared private endpoint and same credentials/config across workers. Use no public listener, no eviction, finite client timeouts and fail-closed outage behavior. |
| Expo provider credential | Worker only where supported | Scope to the correct environment/project, keep out of API service if possible, rotate through the provider without logging the value. |

Generate keys with a cryptographic random generator in a trusted secret
manager. Verify distinctness in the secret manager without printing values.
Separate staging and production scopes. Restrict production secret read to
named operators; require MFA and a second reviewer for access grants. Alert on
secret read/export, service identity changes and recovery-key access.

Do not rotate existing JWT or encryption values automatically. Before every
rotation, identify which stored data/tokens depend on the key, whether dual-key
read is supported, how long both values are needed, and what happens to active
sessions or push tokens. Current one-key settings do not provide transparent
key-ring rotation. Preserve encrypted old-key backups only under an approved
recovery policy and destroy them when their retention expires.

## TLS, ingress and proxy trust

- Enforce HTTPS at the actual public edge; redirect or reject HTTP. Verify
  certificate issuance and renewal for the selected domain before opening
  traffic. Use TLS to PostgreSQL with full certificate and hostname validation.
- Redis on the same host may use the configured Unix socket with restrictive
  owner/group/mode. A remote Redis endpoint must be private, authenticated and
  TLS protected; first resolve the current backend restriction on DNS names.
- Behind Caddy on one host, bind Uvicorn to `127.0.0.1` and trust only the local
  proxy peer. Behind a managed edge, configure the exact documented proxy CIDR
  or direct peer and test forged `X-Forwarded-For` requests from both trusted and
  untrusted sources. Never use wildcard proxy trust. Do not independently parse
  forwarded headers in application code.
- Keep CORS closed for the native app. A future browser client requires a
  separate exact-origin allowlist and CSRF/session design review; bearer token
  behavior alone is not justification for permissive CORS.
- Keep Swagger, ReDoc and OpenAPI disabled in production unless a separate
  reviewed exposure policy is approved. Do not expose admin routes to public
  browser navigation.

## Database and Redis permissions

Create a non-login or tightly restricted migration owner and a separate runtime
role. The runtime role must not own the schema, create roles, install
extensions, alter tables or access unrelated databases. Grant only required
sequence usage and table DML, including cascaded deletion behavior, and test
account deletion, migrations, notification operations and admin audit writes
with the actual roles in an isolated PostgreSQL environment before deployment.
Do not assume PostgreSQL foreign-key cascades work with an untested privilege
set. Do not grant superuser to the API or worker.

The SQLAlchemy PostgreSQL engine now caps each process at 5 pooled connections
plus 2 overflow, with finite pool wait and pre-ping. Size provider connection
limits for API replicas/workers, notification worker, migration job and admin
operations together. Do not raise process or pool counts without recalculating
the aggregate cap and load testing on staging.

Use separate API and worker service identities, environment scopes and
connection credentials. The API handles all user-facing DML. The worker needs
only the database operations required to materialize occurrences, read the
minimal notification context, update delivery rows and heartbeat state; build
and test an explicit table/sequence grant set before using a worker role. The
worker currently imports common settings that require `JWT_SECRET_KEY` even
though it does not mint JWTs. Treat this as a blocker to least-privilege secret
separation; do not share an all-secrets environment file or assume the worker
needs the API signing key for its function.

PostgreSQL should have private network access only where the selected provider
supports it. If a public endpoint is unavoidable, limit ingress to fixed service
egress addresses, require validated TLS, monitor allowlist changes and document
the exposure exception. Disable unneeded database extensions and public roles.

Redis must be shared across API processes and only reachable from the approved
service network/socket. Set a capacity policy that does not evict rate-limit
keys; monitor memory and evictions. Do not use Redis `MONITOR`, expose port 6379
to the internet, share it with staging, or flush it during operations. API
startup and protected requests fail closed when Redis is unavailable; alert on
that condition.

## Admin, support access and privacy

Keep `ADMIN_API_ENABLED=false` until v2 sessions, TOTP key provisioning,
independent admin provisioning, access reviews, audit retention and alerting
are operational. Admin provisioning is an offline command and must run from a
controlled shell using a reviewed database target. Never expose provisioning
commands through HTTP or build output.

Operational admins see bounded metadata and redacted delivery state only.
Financial support inspection requires a superadmin's target-specific,
time-limited grant, reason, case reference, fixed scope, fresh TOTP per read,
read-only access and audit event. Self-approval is exceptional and must page
the configured security/privacy owners. No bulk export, impersonation, payment
editing or recovery of deleted user data is allowed. Keep the approved 12-month
audit retention as a pending production/legal configuration; do not describe it
as enforced until verified.

Account deletion is a transaction-backed hard delete, but old snapshots can
resurrect data. A restore must replay complete post-snapshot WAL/deletion history
in quarantine before service. If the deletion history is incomplete, do not
activate the restore; escalate to the privacy owner and use the approved recovery
decision. External deletion requests and store-policy wording require a real
operated channel and legal review.

## Security incident actions

For suspected key or account compromise: restrict hosting access, preserve
redacted audit/edge evidence, disable affected admin access or notification
delivery when safe, rotate only the affected key under its approved runbook,
revoke affected sessions, assess database and provider access, and notify the
security/privacy owner. Do not dump environment variables or request bodies as
incident evidence. Preserve only evidence authorized by the privacy and legal
process.

For Redis outage, do not switch to process-local memory. Restore shared Redis,
verify private connectivity, then test a protected route and a quota response.
For database outage, stop migrations and worker retries from becoming an
unbounded load; recover from the managed service or isolated restore plan. For
push-provider compromise, revoke the provider credential and pause delivery;
never expose raw device tokens during investigation.
