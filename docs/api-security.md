# Phase 2b.5 — Rate limiting and API security

The user approved Redis shared storage and these configurable initial defaults on 2026-10-21. This phase preserves the uncommitted Phase 2b.1–2b.4 baseline on `mohamed/backend`, HEAD `2b13e37c4ed6800f69915a97416d97b25bf0dd12`. It does not provision production infrastructure or establish production readiness.

## Enforcement policy

| Category | Default | Scope |
| --- | --- | --- |
| Failed/in-flight login | 5 / 900 seconds | Normalized account + canonical source IP pair |
| All login attempts | 30 / 900 seconds | Source IP, across accounts and outcomes |
| Registration | 5 / 3,600 seconds | Source IP |
| Financial writes | 60 / 60 seconds | Authenticated user, shared across profile PATCH and obligation POST/PUT/DELETE |
| Financial reads/evaluations | 120 / 60 seconds | Authenticated user, shared across profile GET, obligation list/detail GET, dashboard, forecast and affordability |
| Forecast | Additional 30 / 60 seconds | Authenticated user; also consumes read quota |
| Affordability | Additional 10 / 60 seconds | Authenticated user; also consumes read quota despite using POST |

These are rolling windows, not fixed clock buckets. Atomic Redis Lua first checks all applicable buckets, then charges all of them or none. Each admitted request uses a globally unique member and Redis server time, preventing worker clock differences and concurrent check/increment races. Keys expire automatically. Rejected requests do not extend existing window expiry. Cluster/Sentinel/replica failover support is not implemented; the selected architecture is one shared standalone service on the VPS. [Redis atomic scripting documentation](https://redis.io/docs/latest/develop/programmability/eval-intro/)

Login reserves a pair slot before Argon2 verification. In-flight attempts count immediately. Failed attempts retain their entry; successful attempts release only their own entry, without clearing earlier failures. Busy/failed verification also releases its own reservation when the backend is available. A crashed worker can leave a reservation until its finite window expires. There is no permanent/global per-account lockout. Different IPs do not share the account-pair lock, while users behind the same IP can affect one another through the IP guard.

Auth IP admission occurs before body parsing/verification. Invalid/duplicate auth requests count; an oversized/unsupported-encoding body can be rejected by the outer guard before admission. Slash and canonical auth URLs share the same bucket; following an HTTP redirect can consume a second IP admission because it makes a second HTTP request. Financial admission occurs after signature/expiration validation and backend user lookup, before endpoint queries/mutations. Subsequent validation failures, ownership 404s and database failures count as admitted requests. Unauthenticated/forged tokens cannot debit another user's quota. Invalid path/method requests that do not invoke authentication are left to routing and edge protections. Health/docs do not consume financial quotas.

429 responses retain the mobile `{"detail":"..."}` error shape and include positive, rounded-up `Retry-After` seconds. They disclose neither account existence nor identifiers. Unknown and known login accounts receive the same 401 and quota behavior. One equivalent Argon2 verification uses the real hash or a random process-held dummy hash, reducing the old unknown-account timing distinction. This is not a claim of constant end-to-end timing, particularly with historical hashes using different costs.

Password hashing/verification is bounded to two operations per worker, waiting at most 0.25 seconds for admission; overload returns safe 503 with Retry-After: 1. This covers registration hashing and login verification. Aggregate concurrency is the worker count times this setting. Existing hashes are never rewritten and JWT secrets, algorithm, token shape and default 60-minute expiration remain unchanged. The existing duplicate-registration 409 contract is explicitly retained, with its existing enumeration risk, as approved.

## Storage and failure behavior

Production defaults to Redis and rejects memory mode. `RATE_LIMIT_REDIS_URL` must explicitly name an absolute Unix socket, a private literal IP/localhost, or an authenticated `rediss://` DNS endpoint. DNS endpoints additionally require `RATE_LIMIT_REDIS_ALLOWED_CIDRS`, a comma-separated list of narrow RFC1918 or IPv6 ULA networks (`/16` or narrower for IPv4, `/48` or narrower for IPv6). Plain `redis://` DNS, missing auth, public/private-shared ranges, broad networks, query options and fragments are rejected. DNS answers are resolved with a bounded deadline on each new connection; every A/AAAA address must be in the configured allowlist, and the actual socket connects to that validated IP rather than resolving the name again. TLS certificate and hostname verification are always required. DNS validation alone does not prove a provider network is private: use provider firewall/VPC rules, egress restrictions and staging verification, and do not allow the Redis endpoint from untrusted networks. A provider DNS change outside the configured CIDRs fails closed. Literal public/wildcard addresses remain rejected. IPv4-mapped IPv6 client identities normalize to the same IPv4 value; other IPv6 addresses normalize to canonical form. Missing/invalid production limiter configuration prevents app import; unavailable Redis prevents lifespan startup. All workers must receive the same Redis endpoint/database, CIDR allowlist, HMAC key and policy settings. Do not disable lifespan startup in the deployment launcher.

Runtime backend failures, connection-pool exhaustion, permission errors and no-eviction memory failures become generic 503 with Retry-After: 1, never a fallback or silent bypass. A failed release after successful password verification also fails safely instead of issuing a token without completing limiter bookkeeping. `/health` remains process liveness and can return 200 during a Redis outage. `/ready` is a separate, undocumented binary probe: it returns only `ready` or `unavailable`, checks PostgreSQL, exact Alembic heads and required Redis, and never returns component errors or addresses. Restrict `/ready` to infrastructure probes at the edge where possible; it does not grant access to admin status or application data.

Keys contain HMAC-SHA256 digests of identities, plus fixed category prefixes. Redis never receives raw emails, IPs, passwords, tokens or user IDs. The dedicated limiter key must be securely generated and separate from the JWT key. Settings repr and error messages omit values. Digests are pseudonymous identifiers, not anonymous data, and retain their associated quota entries for only the active window. No financial database tables or migrations are added.

Development/test defaults to a thread-safe in-memory backend with a fixed 10,000-active-key capacity and finite windows. Saturation returns 503 rather than evicting active limits. It is intentionally process-local, resets on restart, and is rejected in production. Its ephemeral HMAC material affects only local quota identity; it never rotates the JWT signing key.

Redis history loss (restart without durable state, eviction, operator deletion or changing the HMAC key) can reset quotas. The inactive private-socket configuration uses noeviction and AOF everysec; a crash can still lose recent history. Persistence is not an absolute guarantee of quota durability. Configuration changes also require coordinated workers and a reviewed rollout. Distributed attacks/IP rotation remain possible; there is deliberately no account-wide lock that an attacker could use to deny access globally.

## Configuration reference

Only the process environment is read, using the existing explicit Uvicorn `--env-file` mechanism for local files. No automatic dotenv discovery and no real environment edits occur.

| Variable | Default | Validation |
| --- | --- | --- |
| RATE_LIMIT_BACKEND | redis in production; memory otherwise | redis or memory; memory forbidden in production |
| RATE_LIMIT_REDIS_URL | none | Required for redis; private literal IP/localhost or absolute Unix socket; no query/fragment |
| RATE_LIMIT_REDIS_ALLOWED_CIDRS | empty | Required for managed DNS Redis; comma-separated narrow RFC1918/IPv6 ULA subnet allowlist; every DNS answer must fit; TLS and Redis password required |
| RATE_LIMIT_HMAC_KEY | none for Redis; ephemeral local memory key otherwise | Explicit secure random material, at least 32 UTF-8 bytes, placeholder/weak-value checks; distinct from JWT key |
| RATE_LIMIT_LOGIN | 5 | Integer 1–100,000 |
| RATE_LIMIT_LOGIN_IP | 30 | Integer 1–100,000 |
| RATE_LIMIT_LOGIN_WINDOW_SECONDS | 900 | Integer 1–604,800 |
| RATE_LIMIT_REGISTRATION | 5 | Integer 1–100,000 |
| RATE_LIMIT_REGISTRATION_WINDOW_SECONDS | 3600 | Integer 1–604,800 |
| RATE_LIMIT_WRITES | 60 | Integer 1–100,000 |
| RATE_LIMIT_READS | 120 | Integer 1–100,000 |
| RATE_LIMIT_FORECAST | 30 | Integer 1–100,000 |
| RATE_LIMIT_AFFORDABILITY | 10 | Integer 1–100,000 |
| RATE_LIMIT_FINANCIAL_WINDOW_SECONDS | 60 | Integer 1–604,800; shared by all financial buckets |
| RATE_LIMIT_REDIS_TIMEOUT_SECONDS | 1 | Finite, positive, at most 5 seconds; connect/socket timeout, no automatic retry |
| API_MAX_BODY_BYTES | 65536 | Integer 1–1,048,576 |
| API_MAX_JSON_DEPTH | 64 | Integer 1–128 |
| API_BODY_TIMEOUT_SECONDS | 10 | Finite, positive, at most 300 seconds |
| AUTH_ARGON2_CONCURRENCY | 2 | Integer 1–32 per worker |
| AUTH_ARGON2_WAIT_SECONDS | 0.25 | Finite, positive, at most 5 seconds |

The upper configuration ceilings are implementation guards, not recommendations to raise the defaults. Load-test changes against the selected VPS and coordinate every worker. Redis connection pools are bounded to 32 connections per worker.

Placeholder-only production configuration (never copy secret values into logs/chat):

```dotenv
APP_ENV=production
API_DOCS_ENABLED=false
JWT_SECRET_KEY=<existing-secure-JWT-key-in-secret-management>
RATE_LIMIT_BACKEND=redis
RATE_LIMIT_REDIS_URL=unix:///run/dabbarha/limiter.sock
RATE_LIMIT_HMAC_KEY=<separate-secure-random-key-in-secret-management>
```

Both placeholder keys deliberately fail validation. Preserve the existing JWT key. Do not generate or rotate deployment secrets through this phase. `.env.production.example` contains blank secret fields and intentionally cannot start until configured privately. For local development set APP_ENV=development explicitly, keep the existing configured JWT secret and use RATE_LIMIT_BACKEND=memory (default). For local shared-Redis testing, select redis and configure an explicit separate synthetic/private limiter key and socket URL.

## Request and response protection

The outer ASGI middleware checks declared and actual body bytes before JSON parsing, including absent/misleading Content-Length and chunked input. Oversize returns 413; malformed/conflicting length returns 400. Buffering uses bounded bytes rather than an unbounded collection of chunks. A total body-read deadline returns 408. Nesting above 64 returns safe 422; escaped brackets/quotes in Unicode strings do not count. Existing malformed-JSON handling and sanitized validation errors remain. Compressed request bodies return safe 415; gzip response negotiation is unaffected. No user text is sanitized, rewritten or transliterated.

All HTTP responses passing through the application guard, including errors, receive X-Content-Type-Options: nosniff, Cache-Control: no-store and Referrer-Policy: no-referrer. Existing Allow and WWW-Authenticate headers survive. No irrelevant CSP/frame headers or blanket HTTPS redirect are added to break development docs. Existing environment policy still governs Swagger/ReDoc/OpenAPI, with production docs disabled by default.

CORS remains closed: no origin/credentials permissions are added, and browser preflight is not granted. Native React Native requests with bearer tokens continue to work. A future browser dashboard needs a separately approved exact origin allowlist. CORS is not authentication or a network abuse control.

Unhandled application exceptions return generic JSON 500 and log only the constant category `api_request_failed`, without exception strings, traceback, bodies, headers, URLs or identifiers. Existing SQLAlchemy and validation handlers remain safe. No request/body logging is introduced. External SQLAlchemy echo, tracing/error collectors that capture locals, server debug/trace and proxy logging can still leak data if independently enabled; deployment must keep these disabled or separately redact them. Failures after response streaming has begun cannot be replaced by a new status; this API currently has no streaming/upload endpoint.

Valid JSON keys, Decimal responses, Unicode text, optional financial-profile defaults, protected ownership and financial calculation formulas are unchanged. Added abuse/resource errors are 429/503/413/408/415 and invalid-length 400; deeply nested JSON returns 422. The read-only frontend's Axios handler understands detail strings/arrays. No frontend build/runtime test or automatic retry/UI work was performed; clients can read Retry-After but must avoid blindly replaying financial writes after network errors.

## Deployment boundary (templates are inactive)

`deploy/redis.conf.example` has **port 0**, a private Unix socket and restrictive socket permissions. Arrange service ownership/group access, writable private runtime/persistence directories, patch management, resource limits and backups through an approved deployment process. Do not expose port 6379 publicly. For network access instead, firewall/bind to the private interface only, configure ACL authentication and verified TLS with rediss where applicable. The Unix example relies on filesystem access control; this phase installs no service or credentials. [Redis security guidance](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)

`deploy/Caddyfile.example` is for direct clients -> Caddy HTTPS -> loopback Uvicorn. It replaces forwarding data from the actual connection, discards unused Forwarded/X-Real-IP, limits bodies/headers and configures read/response timeouts. Uvicorn must explicitly trust only Caddy's loopback connection; never use forwarded-allow-ips '*'. Application code derives identity from ASGI connection context and does not parse arbitrary forwarding headers. No CDN trust is assumed. Additional proxies/CDNs require a new explicit review. [Caddy forwarding behavior](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#defaults)

HSTS exists only in the HTTPS proxy example, without includeSubDomains/preload. Validate HTTPS/hostname/certificate ownership before activating it. The application itself emits no HSTS on local HTTP. The sample proxy header ceiling is 16 KiB and header-read timeout 5 seconds; review against the selected supported Caddy release. Caddy-generated errors may use proxy response formats rather than application JSON, and transport-level parse failures occur outside ASGI. The template was reviewed against official documentation but was not executed/validated with a Caddy binary or live TLS. [Caddy options](https://caddyserver.com/docs/caddyfile/options), [body limit documentation](https://caddyserver.com/docs/caddyfile/directives/request_body)

Illustrative launcher after private configuration and deployment review (paths/worker capacity require selection; do not run against persistent data during this phase):

```sh
<clean-runtime>/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1 \
  --limit-concurrency 64 --timeout-keep-alive 5 --timeout-graceful-shutdown 30 \
  --no-access-log --no-server-header
```

Two workers / 64 concurrent connections per worker are illustrative starting capacities for benchmarking, not validated production sizing. Use the same private Redis/key/policy in every worker, no reload, no public backend port, and only the selected HTTPS hostname at the proxy. The example does not enable access logs; do not enable log_credentials/debug/trace or credential/query capture elsewhere. Define log retention and private aggregate monitoring in deployment. Production still requires a supported security-patched CPython 3.12 and a separately approved PostgreSQL deployment; this phase retains local SQLite and does not install a PostgreSQL driver.

The body timeout covers upload reading, not the whole financial operation. Proxy deadlines and Uvicorn keep-alive timeouts do not terminate synchronous Argon2/SQLAlchemy work. The existing 60/1,200-month bounds and rate/admission limits reduce work, but obligation row count, database statement timeouts, pagination, volumetric edge protection and load testing remain future work. There is no idempotency or concurrency-control redesign.

## Verification

Use the new clean Phase 2b.5 environment (not the original vulnerable `.venv`):

```sh
REQUIRE_REDIS_TESTS=1 REDIS_SERVER_BINARY=/absolute/path/to/redis-server \
  PYTHONDONTWRITEBYTECODE=1 <clean-verify-venv>/bin/python -m pytest -q -p no:cacheprovider
```

The integration fixture starts its own disposable server with TCP disabled and a mode-700 Unix socket; it never connects to or flushes an existing service. Without a server binary, normal local tests explicitly skip Redis integration cases; REQUIRE_REDIS_TESTS=1 makes that absence a failure. Current verification enables it and has no skipped tests. Memory tests also cover expiry and atomic admission with a controlled clock.

Actual Redis integration covers concurrent threads, three independent spawned processes sharing one quota (exactly 7 of 30 admissions), finite expiry, reservation release, API admission on the Redis runtime, private port-zero configuration, startup connectivity and missing-service failures. It does not simulate an actual Linux multi-worker Uvicorn network deployment or Redis failover. Other cases cover independent users, ownership, login account/IP behavior, forged forwarding headers and Uvicorn trust, Argon2 waiting/capacity, chunked/false-length/oversize/slow input, nested JSON/Unicode, safe errors/logs, security headers, CORS and all existing valid financial/authentication behavior.

Dependency verification: redis **8.1.0** is the only new Python distribution; all 40 existing app/test distributions retain their versions. pip remains 26.2.2. The separate **Redis server 7.4.11** test build matches official published SHA-256 `3c266ece0abd54ed3b1c912c6eb86b7508cf382cb690ee6649d3843f018f6357`. Linux CPython 3.12/Ubuntu 24.04 x86_64 wheel/marker closure and all 41 published wheel hashes were verified, followed by complete offline hash-lock replay and exact requirements-resolution comparison. No Linux/PostgreSQL/Caddy execution is claimed.

The OSV pip-audit scan reports **42 distributions scanned, zero known advisories, zero skips**. The baseline Phase 2b.3 Python environment also had zero findings; this phase adds no unresolved Python advisory. The scan does not certify the Redis daemon, proxy, operating system or future deployments. `pip check`: no broken requirements. Full clean-environment suite: **485 passed, 1 warning in 32.01s**, no skips (433 existing tests + 52 new security regressions). Final diff/status is recorded in the verification report.

## Files and remaining review

- `app/core/api_security_settings.py`: validated configurable security policy.
- `app/core/rate_limit.py`: atomic Redis sliding windows, bounded local store, HMAC keys and safe errors.
- `app/core/api_security.py`: authenticated/category/IP admission and per-worker Argon2 slots.
- `app/core/request_security.py`: streaming input guards, safe headers and error-log suppression.
- `app/main.py`: security runtime, startup/cleanup and middleware integration; prior policies retained.
- `app/core/security.py`: ephemeral dummy Argon2 hash for unknown-account verification.
- `app/api/routes/auth.py`: login reservations/equivalent verification and bounded registration hashing.
- `app/api/deps.py`: financial admission after authenticated user lookup; extreme signed subject IDs safely rejected with 401 before database binding.
- `requirements.txt`, `constraints-python312.txt`, `requirements-linux-py312.lock`: reviewed client and reproducible pins/hashes.
- `tests/test_api_security.py`: 52 new regression cases; `tests/conftest.py`: isolated per-test quotas.
- `tests/test_settings.py`, `tests/test_v1_release.py`: explicit synthetic production limiter configuration for prior regressions. Only the no-AI import test stubs connectivity; actual storage tests are separate.
- `.env.example`, `.env.production.example`: safe local guidance and intentionally incomplete production template.
- `deploy/Caddyfile.example`, `deploy/redis.conf.example`: inactive operational examples.
- `docs/configuration.md`, `docs/dependencies.md`, `docs/api-security.md`: integration, dependency and operational documentation.
- `PROGRESS.md`: verified completion entry added only after successful checks.

Remaining risks include registration enumeration, residual timing variability, shared-IP throttling, distributed/rotating-IP attacks, Redis history loss and single-service availability, policy/key inconsistency across workers, unbounded obligation count, no synchronous work cancellation or idempotent retry guarantee, and external logging/proxy/deployment configuration. Do not claim production readiness from the passing tests or dependency scan.
