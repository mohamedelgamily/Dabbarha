# Monitoring and alerting design

Status: monitoring plan only. No production monitoring account, alert, dashboard,
on-call rotation, or external uptime check exists as a result of this work.

## Signals and health endpoints

`GET /health` returns the process liveness response and does not query PostgreSQL
or Redis. During startup the FastAPI lifespan pings Redis and refuses to start
when it is unavailable; a later Redis or PostgreSQL failure does not make
`/health` change. Do not use it as a dependency-readiness result.

`GET /ready` is the infrastructure dependency probe. In production it requires
PostgreSQL (SQLite is retained for local development/tests), checks a read-only
database query, exact current Alembic heads and Redis connectivity when Redis
is required. It returns only a fixed `ready` body or a generic 503 `unavailable`
body; no dependency name, hostname, credential, driver message or financial
data is included. It is omitted from OpenAPI. Limit ingress to configured
platform probes where feasible and never use this endpoint to display operational
details.

`GET /admin/ops/health` reports API, database, Redis, migration, notification
worker heartbeat and non-secret configuration status, but requires the admin
API to be enabled and a current MFA-verified administrator. Do not make it
public or bypass MFA for a platform probe. `/health` is liveness only; a
separate authenticated synthetic check remains necessary for end-to-end
behavior. The synthetic job must keep credentials in a secret manager, never
emit them, and use a disposable staging account. Admin health is useful for
human operations review when admin is intentionally enabled.

The notification worker writes account-free heartbeat rows and cycle metrics.
Check the heartbeat age from a trusted monitor and alert on stale age rather
than only checking whether the process exists. The worker catches cycle errors
and continues, so a running process alone is not proof of successful work.

## Telemetry policy

Use structured event records with an allowlist of fields: timestamp, service,
environment, release SHA, severity, stable event name, sanitized component,
duration, count, status code and generated correlation ID. The current API
failure handler logs only `api_request_failed`; the worker logs fixed event
names, counts and exception class. Do not expand those handlers to log exception
text or stack traces without a reviewed sanitizer.

Never collect bearer or refresh tokens, cookies, passwords, TOTP codes, raw push
tokens, full database/Redis URLs, encryption keys, request/response bodies,
financial values, item names, emails, support case references, or user-linked
deletion data. Exclude authorization and `X-Admin-TOTP` headers from proxy,
APM, tracing and error reporting. Keep Caddy access logging disabled unless its
format has been reviewed to remove query strings, sensitive headers and IDs.
Use short-lived operational logs with access audit and automatic deletion;
set a documented retention period and legal hold process before launch.

The app currently uses standard Python logging rather than a structured JSON
logging dependency. A platform collector may parse the fixed `key=value` worker
events, but must not enrich them with user identities. Do not add a logging
agent or dependency until the target platform and retention controls are chosen.

## Initial alert matrix

Thresholds below are starting operational targets, not measured SLOs. Confirm
them after staging load tests and assign an on-call owner.

| Signal | Initial alert | Response |
|---|---|---|
| External HTTPS uptime | 2 consecutive 1-minute checks fail; page on-call | Check edge, API liveness, DNS/certificate and provider status. |
| API server errors | 5xx above 2% for 5 minutes or any sustained 503 from protected storage paths | Correlate release and database/Redis health; preserve redacted event IDs. |
| PostgreSQL | connection failures immediately; connections >80% of configured max for 5 minutes; disk >80% warning and >90% critical; CPU >85% for 10 minutes | Check pool sizing, slow query insights, storage growth and provider failover. Do not dump SQL bind values. |
| Redis limiter | unavailable once from monitor or repeated protected-route 503; memory >70% warning, >85% critical; any eviction is critical | Check private endpoint, credentials, capacity and no-eviction configuration. Do not switch to memory mode. |
| Worker heartbeat | no successful cycle/heartbeat for 2 minutes (baseline worker poll is 5 seconds) | Check process supervisor, DB connectivity, stale leases and safe error class counts. |
| Push deliveries | failed/unknown count rises for 10 minutes or failure ratio exceeds 10% in a 10-minute window | Check provider status and aggregate error codes; pause delivery if credentials may be exposed. Never log token/payload. |
| Session/auth abuse | sustained 429/401 increase, login quota saturation or unusual refresh conflicts | Verify edge and rate limiter; do not disable quotas to restore traffic. |
| Account deletion | database/lock 503 or errors persist for 5 minutes; alert on any deleted-account authentication success | Confirm transaction outcome, cascading cleanup and worker lock state; involve privacy owner. |
| Admin security | any self-approved support grant, admin role/key change, or repeated denied finance read | Page security/privacy owner; review the target/case-bound audit trail under authorized process. |
| Backup/restore | missed backup, retention policy drift, WAL archive gap, failed restore drill | Block release or recovery cutover until a verified recovery path exists. |

Do not call proposed metrics a service-level objective until availability,
latency and recovery performance are measured and formally approved.

## Uptime and synthetic checks

Use an external HTTPS uptime monitor for `/health`; it proves only that the
process responds. Add a separate scheduled synthetic from a protected runner
that signs in to a disposable staging account, reads profile/dashboard/forecast,
and verifies a deterministic test plan. Never execute mutating or deletion
checks against a real user. A successful generic DB/Redis connection check may
be run from private network monitoring, but it must not print connection URLs.

Run a dependency probe against the protected API to catch 503 behavior, and use
provider-native PostgreSQL/Redis metrics for pool saturation, storage, latency,
replication and evictions. For the worker, alert from heartbeat age and
notification-delivery aggregates. Separate staging alerts from production and
test notification delivery to the on-call channel before launch.

## Incident response and review

Maintain named primary/secondary on-call contacts, provider escalation details,
severity definitions, and runbooks for API outage, DB/Redis failure, push failure,
key exposure, account deletion incident, data restore and admin misuse. Test
alert delivery quarterly and run a tabletop before public launch. Every alert
must state service/environment, stable incident ID, component and safe action;
it must not include customer data or secrets.

Review alert noise, threshold misses, access logs and retention monthly. Record
decisions and evidence with the release. Admin audit retention and alerts for
self-approved access remain pending the approved privacy/legal retention policy
and operational alert configuration.
