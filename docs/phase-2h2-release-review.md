# Phase 2h.2 release review

## Dependency remediation and verification

The external Phase 2h.1 log stopped at pip-audit on dnspython 2.8.0.
[CVE-2026-114605](https://github.com/advisories/GHSA-45c3-73f7-pv4m)
affects DNS name parsing before 2.9.0.
[CVE-2026-128089](https://github.com/advisories/GHSA-vvf4-9x63-8xvv)
affects WKS text parsing before 2.9.2. Both can exhaust resources.
The only application pin changed is dnspython. The downloaded
dnspython-2.9.2-py3-none-any.whl matched the [PyPI digest](https://pypi.org/pypi/dnspython/2.9.2/json)
af15f7d385a6ae2fb35a796fde2138004c8c42c7389090e2addc83e3b3340fd8.
The universal wheel requires Python >=3.11. constraints-python312.txt controls
the cross-platform install through requirements.txt. requirements-linux-py312.lock
pins the same wheel for Linux. Pydantic EmailStr uses email-validator with
deliverability checks disabled. app/core/private_redis.py directly uses the DNS
resolver for A/AAAA with one deadline, rejects the whole answer on any disallowed
address and connects to a validated IP with TLS verification for the hostname.
The app does not accept zone files. Existing email, resolver, TLS and outage
tests exercise the compatibility boundary without adding attack fixtures.

From Mac Terminal run:

    cd ~/Projects/dabbarha-backend && bash scripts/run-phase-2h2-verification.sh

Each invocation creates a new venv, checks the wheel against the lock, installs
the pinned stack and delegates to the 2h.1 runner. Keep the original venv for
comparison. Review the emitted log for 44 matching pins and hashes, clean audit,
pip check, 21 Windows helper cases, seven focused service/migration cases,
756 total passes, zero skips/errors and clean Git/artifact checks. The Windows
guide covers owner-only ACL setup, idempotent secret generation, explicit
SQLite path confirmation and restart/refresh/logout. Native Windows and phone
testing remain pending. No authentication or financial API changes are required.

## Browser admin audit

Only mobile/package.json exists in the inspected frontend. The backend has
admin route modules and CLI provisioning. No separate web UI or browser API
integration was found for any capability below. Security evidence is backend
coverage in tests/test_sessions.py and tests/test_admin_operations.py. Browser
storage, request behavior and operator workflow still require acceptance tests.

| Capability and backend evidence | Minimum browser work and acceptance | Launch impact |
|---|---|---|
| V2 password login, TOTP step-up, role and session binding (routes/sessions.py, routes/admin.py) | Dedicated admin origin, sign-in and step-up screen. Design browser credential storage, CSRF and XSS controls before integration. Test ordinary user, expired MFA and revoked role denials. | Required for browser access |
| Operational overview and health (admin.py) | Overview with honest unavailable metrics and stale worker state. Exercise DB/Redis outage. | Operational visibility required |
| Exact user lookup and bounded sessions (admin.py) | Single exact lookup, metadata allowlist, pagination, 429 handling. Test no wildcard, no financial detail. | UI deferrable |
| Redacted delivery diagnostics (admin.py) | Read-only status, safe errors and pagination. Test responses never disclose push tokens. | Equivalent push diagnostics required |
| Case approval and financial reads (admin_support.py) | Separate superadmin workflow, target, reason, case, bounded scope, explicit exceptional self-approval. Test five-minute target/session MFA, max 15-minute grant, expiry, revoke, no export or mutations. | Blocker if support inspection enabled |
| Audit and provisioning (admin_access.py, admin-security.md) | Keep provisioning offline. Route alerts and review exceptional grants through restricted operations tools. No general audit browser assumed. | Required if admin enabled |
| Logout and device revocation (sessions.py) | Server logout, clear local state, password-confirmed device revocation. Verify denied subsequent reads with old credentials. | Required for browser access |

Implement identity and logout first, then read-only operations, then case-bound
support. Security and privacy owners approve support workflow before exposure.
A browser UI can follow mobile launch if named operators demonstrate equivalent
MFA-protected diagnostics, alerts, revocation and incident response. Keep
unneeded admin features disabled and keep admin functions outside the mobile app.

## Provider-neutral deployment gaps

Status refers to evidence available before provisioning. Systemd and Caddy
examples describe a VPS topology. Capacity starts with one API service and one
separate supervised worker. Size from Argon2 concurrency, worker batch timing
and staging load. Budget up to seven PostgreSQL connections per process
(pool five plus two overflow) plus migrations, operator connections and reserve.

| Severity / state | Evidence and consequence | Owner, dependency, required action and acceptance |
|---|---|---|
| High / owner decision | production-architecture.md. Region, latency to Egypt, data residency and spend are undecided. | Owner + privacy approve region, budget and provider after reviewing managed PostgreSQL, private Redis and recovery support. Record comparison and staging latency. |
| High / staging needed | deploy/*.service.example, worker.env.example. Shared credentials or failed supervision expose data or stop reminders. | Infrastructure after provider approval: isolate staging/prod networks, databases, Redis, domains, Expo projects, service identities and secret stores. Validate units on Ubuntu 24.04, restart API and worker independently and deny worker access to JWT/receipt/admin keys. |
| High / staging needed | private_redis.py, redis.conf.example. Public endpoints, mixed DNS answers, rotating addresses outside allowed ranges and certificate mismatches stop protected requests. | Infrastructure requires private DNS with stable approved RFC1918 /16 or narrower or ULA /48 or narrower, authenticated TLS and valid hostname certificate for managed DNS. Reject incompatible plans. Prove private-only ingress, failover/re-resolution, shared quotas and outage 503. |
| High / staging needed | Caddyfile.example, deployment-runbook.md. Proxy trust and incorrect TLS routing affect access and quotas. | Infrastructure after DNS delegation: validate Caddy on Linux, restrict direct API ingress, enforce HTTPS and trusted proxy scope. Test certificate renewal, header handling and request limits. |
| High / staging needed | app/db/database.py, alembic/, deployment-runbook.md. Excess connections or bad grants/migrations interrupt service. | DBA on private managed PostgreSQL: enforce verified TLS, separate API/worker/migrator grants, load-test pool budget, deny runtime DDL. Review SQL, verify backup, rehearse upgrade and compatible app rollback on synthetic staging data with approval. |
| High / missing operational proof | backup-and-restore.md, account-deletion.md. Restores can resurrect deleted data. | DBA + privacy after backup provisioning: encrypt scheduled backups/PITR, enforce <=30 days, approve proposed 15 min RPO/4 h RTO, restore in isolation and reconcile deletions before reopening access. Record measured recovery and expiration. |
| High / staging needed | monitoring-and-alerting.md, security-operations.md. Silent outages and sensitive logs compromise operations. | SRE after service setup: probe /health and /ready separately, monitor heartbeat, queue, failed sends, auth and elevated grants. Assign on-call, inject outages, verify redaction, alert receipt, restart/recovery and incident escalation. Confirm retention and key rotation with security/privacy. |
| Medium / staging needed | production-smoke-tests.md, payment-reminders.md. Local mocks cannot establish provider delivery or resource limits. | Backend + mobile with staging credentials: exercise registration to deletion, retries, worker restart and real push receipts. Load-test CPU/RAM, DB/Redis limits and rollback before widening rollout. |

Private networking, TLS, scoped identities, independent environments, tested
recovery and actionable alerts are required capabilities. Provider branding,
containerization and an operator browser interface are implementation choices.

## Ordered release gates

1. Backend/QA review the patched Mac run and native Windows smoke evidence.
2. Owner approve infrastructure budget/region, recovery objectives and named
   operators. Infrastructure provision isolated staging only after authorization.
3. DBA/SRE demonstrate networking, grants, schema rehearsal, HTTPS, probes,
   backups, deletion-safe restore, monitoring and rollout/rollback above.
4. Jomana confirm her tested build SHA. Read-only inspection of remote
   jomana/frontend at b2f0d67ed0f3fb96af4887a816431ad9adeef5eb found the V2
   paths in mobile/src/api/sessions.ts and logout.ts. The older local checkout
   uses legacy login. End-to-end integration remains awaiting verification. Against staging
   HTTPS, verify SecureStore, single-flight refresh, restart, logout and account
   isolation. Use frontend-api-contracts.md and frontend-mobile-integration-handoff.md
   for dashboard/obligations, exact schedules, paid/undo, forecast, affordability,
   profile and deletion. Check English/Egyptian Arabic, RTL and cache clearing.
5. Mobile/release verify both physical platforms, denied/granted push permission,
   delivery, receipts, deep links and lock-screen privacy with isolated APNs/FCM
   credentials. Run TestFlight and Play internal builds and record regressions.
6. Privacy/support publish accurate policies and a working externally verified
   deletion channel, test it, review store disclosures and support access/retention.
   Release owner signs off device results, support coverage, store review and
   production rollout separately. No production or store acceptance evidence yet.

Optional later work includes a polished dashboard, richer aggregate analytics
and additional scale-out capacity beyond measured demand. Existing access,
audit and privacy controls apply to any operational alternative.

## Remediation evidence

The isolated CPython 3.12 Mac environment matched all 44 pins and the Linux
lock inventory. pip check passed and pip-audit reported no known
vulnerabilities. A focused run covering registration, Windows setup and Redis
DNS/TLS passed 85 tests. The original environment remains pinned to 2.8.0.
The external acceptance command above requires all applicable integrations.

### Windows setup review

scripts/setup-local-windows.ps1 locates the repository using PSScriptRoot,
invokes the venv interpreter with argument arrays, checks Git tracking and
ignore status, and restricts the local configuration ACL before generating
credentials. scripts/local_windows_config.py rejects linked files, duplicate
assignments and invalid secrets and serializes concurrent setup. It passes a
filtered environment directly to the child interpreter. Ordinary startup checks
the migration marker read-only. The explicit migration command checks the file
identity around confirmation and limits upgrades to the reviewed local path.
These checks assume a trusted, private checkout; do not use a directory writable
by other users. Verify owner-only ACLs, a path containing spaces, cancelled
migration, preserved file hash after a second setup, loopback vs explicit LAN,
and server-side logout on native Windows. API routes, existing migrations and
frontend files have no Phase 2h.2 changes.

Before opening a restored environment, disable push workers and external traffic.
A backup alone cannot establish which accounts were deleted later. Where WAL
or independently authorized deletion reconciliation evidence cannot establish
the correct state, keep the restore isolated and escalate to privacy and the
incident owner. Test this failure path during the staging drill.

The sandbox verification runner stopped with six PostgreSQL readiness fixture
errors because initdb could not allocate System V shared memory. The changed-file
secret and whitespace checks passed.

Patched local suite: 658 passed, 98 skipped, one existing Starlette/httpx
warning. A separate required-service run passed all three real Redis tests
(expiry, shared worker quotas and runtime startup). These results overlap the
external target count and must not be summed.

External Mac verification passed on November 22, 2026. The complete backend
suite recorded 756 passed, 0 failed, 0 skipped and 0 deselected, with exit
status 0. All 21 Windows helper tests passed on macOS and all seven focused
PostgreSQL/Redis integration cases passed. All 44 dependency pins and Linux
lock hashes matched. `pip check` passed and `pip-audit` reported no known
vulnerabilities. One existing Starlette/httpx deprecation warning remains.
Native Windows execution, staging verification and production verification
are pending.
