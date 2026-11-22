# Windows local backend setup

This guide runs the backend on Windows for local Expo development. It uses the
repository's Python 3.12 virtual environment, a private local SQLite database,
an ignored `.env.local`, and an explicit environment passed to Uvicorn. It does not
install software globally, start PostgreSQL/Redis, change Windows Firewall, or
configure production. Local HTTP is for a trusted development network only.

## One-time setup

Open PowerShell in the backend checkout. Use the actual checkout path; the path
below is Jomana's current example and may differ:

```powershell
Set-Location -LiteralPath 'C:\Users\Jojo Zohny\Downloads\Dabbarha-Dev\Dabbarha-Backend'
.\scripts\setup-local-windows.ps1
```

The bootstrap checks that this is the backend Git repository, `.venv` contains
CPython 3.12 and required packages, `pip check` succeeds, and Git ignores
`.env.local`. It creates only missing settings and random secrets. Existing
settings are preserved; an existing empty, placeholder or invalid secret fails
validation and is never replaced. Secret values are not printed. The script
restricts `.env.local` ACL access to the current Windows account. Rerunning it is
safe and does not rotate valid keys.

On the first launch only, the SQLite schema may be behind. Setup reports the
current migration status but does not alter data. Inspect the printed database
path and make a separate backup, then use the explicit `-ApplyMigrations`
startup command below once. Later launches use the everyday command.

If `.venv` is missing, install CPython 3.12, then from the repository root run
these commands once:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then rerun setup. The script does not install or upgrade packages. If PowerShell
blocks local scripts, use a process-only policy for this window (no system-wide
policy change):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

## Everyday backend startup

From the backend directory, the normal command is:

```powershell
.\scripts\start-local-windows.ps1
```

It validates settings, checks Redis only if the local config explicitly selects
Redis, reads the migration version without creating or modifying a database,
then starts Uvicorn on `127.0.0.1:8000`. Stop with Ctrl+C. The script does not
activate the venv. The helper parses `.env.local` once for startup, checks the
selected database, and passes the validated settings to Uvicorn. Inherited
backend settings and dotenv interpolation cannot override the local values.
Use uppercase variable names and literal values. Setup rejects duplicate, bare
or malformed assignments.

The bootstrap defaults to `RATE_LIMIT_BACKEND=memory`, which is the supported
development/test limiter. **V2 device sessions use the database and do not
require Redis.** If you deliberately configure Redis, it must be reachable and its URL and separate HMAC key must be valid. Managed
DNS additionally requires credentials, TLS and a private CIDR allowlist. An
unavailable or misconfigured Redis stops API startup. Production always requires shared Redis and cannot
use the development memory limiter. Do not change production configuration to
make local setup work.

## Local configuration and secrets

The helper creates `.env.local` in the repository root, and verifies that Git
ignores it. `.env`, `.env.local`, and other `.env.*` files are ignored while
`.env.example` and `*.example` templates remain trackable. Never commit or share
`.env.local`, paste its values into chat, or include it in screenshots/logs.
The API reads its process environment. The Windows helper explicitly supplies
that environment from `.env.local` and never searches for other dotenv files.

The required session setup is:

| Variable | Local value/source | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Enables the development policy; production is never inferred. |
| `DATABASE_URL` | `sqlite:///./dabbarha.db` | Existing supported local SQLite mode, resolved from the backend root. |
| `JWT_SECRET_KEY` | Generated once with Python's cryptographic random source | Existing HS256 access-token signing key; at least 32 bytes, and the backend's strict placeholder/strength checks apply. |
| `JWT_ALGORITHM` | `HS256` | Existing signing contract. |
| `SESSION_AUTH_ENABLED` | `true` | Explicitly enables the V2 session endpoints. |
| `SESSION_RECEIPT_KEY` | Generated once as base64 for 32 random bytes | Separate authenticated-encryption key for bounded refresh-response recovery; must not equal the JWT or rate-limit key. |
| `SESSION_RECEIPT_KEY_ID` | `v1` | Key identifier; may be omitted because the backend default is `v1`. |
| `RATE_LIMIT_BACKEND` | `memory` | Bounded process-local limiter for local development. Not valid in production. |

The setup also explicitly enables local API docs and leaves notification
delivery disabled. `NOTIFICATIONS_ENABLED`, `NOTIFICATION_DELIVERY_ENABLED`,
push encryption keys, Expo credentials, admin keys, and Redis secrets are not
needed for this local V2 login flow. The bootstrap will not create those keys.
Do not copy development values to staging/production. Keep existing local keys
unchanged between restarts; replacing them can invalidate local tokens or make
encrypted refresh receipts unavailable. The helper never silently rotates them.

## Database and migrations

The app supports SQLite locally; PostgreSQL is not required for this Windows
workflow. The helper accepts only a persistent SQLite file inside this backend
checkout. It rejects in-memory, external, PostgreSQL, and URI/query database
targets. It does not delete, reset or downgrade a database.

V2 device sessions begin at Alembic revision `6b6a00000001`, which adds
`auth_sessions`, `auth_refresh_tokens` and `legacy_access_revocations`.
The upgrade continues through revisions `2c1a00000001`, `2d1a00000001`,
`2e1a00000001`, `2f1a00000001`, `2f2a00000001` and the current head
`2f3a00000001`.
Later application features add revisions, so the current database must match the
repository's current Alembic head, not merely `6b6a00000001`. Startup checks
`alembic_version` using a read-only SQLite connection. A new DB or a DB with
pending revisions stops startup; it is never migrated automatically.

To inspect a pending local migration, close any running API, note the local DB
path printed by the script, inspect its contents, and make a separate backup
outside the repository. If it is definitely your disposable/local development
database and its data should be retained, explicitly request the additive upgrade:

```powershell
.\scripts\start-local-windows.ps1 -ApplyMigrations
```

The script displays the resolved local SQLite path and requires typing `APPLY`
before it invokes `alembic upgrade head`. It verifies the resulting head and then
starts the API. If the target changes while confirmation is pending, it stops. If the ownership or contents are uncertain, do not confirm; ask
the backend owner to inspect it. No downgrade or production/shared DB migration
is supported by this helper.

## Starting Expo and connecting a physical phone

Start Expo in a separate PowerShell terminal in Jomana's frontend checkout. The
backend's normal loopback bind is not reachable from a phone. For phone testing,
start the backend with an explicit one-run LAN bind:

```powershell
.\scripts\start-local-windows.ps1 -ListenOnLan
```

This binds Uvicorn to `0.0.0.0` only for that run and prints current IPv4 URL
candidates. Choose the Wi-Fi adapter address on the same private network as the
phone; addresses can change. Do not commit an IP address. In the Expo terminal,
set the current address using the frontend's existing variable:

```powershell
$env:EXPO_PUBLIC_API_URL = 'http://<current-wifi-ipv4>:8000'
npx expo start
```

Replace the placeholder locally. Restart Expo after changing the variable. The
frontend may choose simulator defaults when this variable is absent; a physical
phone must use the reachable PC Wi-Fi address, not `localhost`, `127.0.0.1`, or
the Android emulator-only `10.0.2.2` address. Both devices must be on the same
Wi-Fi, and the network must not enable client isolation. A VPN can route traffic
through a different interface. Select the current Wi-Fi address, not a stale IP.

The script does not change Windows Firewall. If Windows blocks the connection,
on a trusted Private profile an administrator may add a narrowly scoped rule for
TCP 8000 from the local subnet only; inspect and remove it after testing:

```powershell
New-NetFirewallRule -DisplayName 'Dabbarha dev API 8000 (Private)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Profile Private
```

After testing, remove the temporary rule:

```powershell
Remove-NetFirewallRule -DisplayName 'Dabbarha dev API 8000 (Private)'
```

Do not use a Public profile or expose this port to the internet. Local HTTP has
no TLS and must not carry real user data. `/health` returning `{"status":"ok"}`
confirms only reachability/liveness; `/ready` reports a minimal dependency
readiness result. Neither replaces an authentication/financial smoke test.
Staging/production use HTTPS and are separate environments.

## V2 backend authentication contract

| Request | Authentication and request | Success / behavior |
|---|---|---|
| `POST /auth/sessions` | Public sign-in; JSON `email`, `password`, optional trimmed `device_label` (1–80 chars). | `200` `SessionToken`: `access_token`, `token_type`, `expires_in`, `refresh_token`, `refresh_expires_at`, `session_id`, `session_expires_at`. New access JWTs default to 15 minutes; refresh inactivity is 30 days, absolute session life 90 days. |
| `POST /auth/refresh` | Public credential exchange; JSON canonical 32-byte base64url `refresh_token` and a separately generated/persisted canonical 32-byte base64url `retry_key`. | `200` same token-pair shape. Rotate with one shared/single-flight client request. Same request can recover the exact response for up to two retries within 60 seconds without extending expiry. |
| `POST /auth/logout` | Feature enabled; send exactly one: `Authorization: Bearer <access token>` and no body, or JSON `{ "refresh_token": "..." }` and no Authorization header. | `204`; server revokes the relevant session/family. Clear client SecureStore and private caches after local logout policy. |
| `GET /auth/me` | `Authorization: Bearer <access token>` from an active V2 session or an accepted legacy token. | `200` current user's profile or `401` for missing, invalid, expired, or revoked credentials. |

Malformed JSON or schema violations return `422`. Invalid authentication returns `401`;
rate limits return `429` with `Retry-After`; unavailable database/security
storage can return safe `503`. Session sign-in has failed/in-flight account+IP
and IP quotas. Refresh has per-session and IP quotas. The app must not tight-loop
on `429`/`503`, and should treat a refresh `409`/`401` as requiring sign-in.
`GET /auth/sessions` lists only the current account's devices, and revoking a
device requires password confirmation. See
[`auth-sessions.md`](auth-sessions.md) and
[`frontend-api-contracts.md`](frontend-api-contracts.md) for exact schemas and
the rest of the mobile API contract.

### Compatibility status to resolve with the frontend owner

The local frontend checkout at `1c144d4` uses legacy login. The remote
`jomana/frontend` revision `b2f0d67ed0f3fb96af4887a816431ad9adeef5eb`
contains V2 session and logout calls. Record the actual device build SHA and
verify session restoration, refresh and logout against this backend.


## Local end-to-end smoke test

Start from a copy of the reviewed backend checkout in a path with spaces.
Before setup, resolve any existing file ownership questions or use a fresh
disposable checkout. Run setup twice and compare the config hash locally.
Only report whether the file stayed identical.

```powershell
.\scripts\setup-local-windows.ps1
$before = (Get-FileHash -LiteralPath .env.local).Hash
.\scripts\setup-local-windows.ps1
if ((Get-FileHash -LiteralPath .env.local).Hash -ne $before) { throw 'Setup changed the local config.' }
.\.venv\Scripts\python.exe -I scripts/local_windows_config.py migration-status --root .
```

Before first upgrade, ordinary startup must refuse a pending schema. Declining the
`APPLY` prompt must leave the database unchanged. With the disposable database
identified, confirm the migration, then verify `MIGRATIONS_CURRENT`. In another
terminal check both probes while the API is serving.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/health'
Invoke-RestMethod 'http://127.0.0.1:8000/ready'
```

Expect `ok` and `ready`. Check that only loopback is listening before opting into
LAN mode. In LAN mode open `http://<current-wifi-ipv4>:8000/health` on the phone
before starting the Expo test. For a backend-only check, use the PowerShell
commands below. See the [API contract](frontend-api-contracts.md) for exact
financial request bodies.

Use a disposable test account and local DB only. In Expo, verify this sequence:

1. Register a development account. Registration returns `201`; profile fields
   are optional and can be completed later.
2. Confirm a protected request without credentials returns 401. Sign in through V2 `POST /auth/sessions`; verify the app stores credentials
   in OS-backed SecureStore, never AsyncStorage.
3. Fetch `GET /auth/me` and confirm the returned profile belongs to this account.
4. Trigger an expired access token; verify one serialized `POST /auth/refresh`,
   the same persisted retry key for ambiguous retries, and atomic replacement of
   both returned credentials.
5. Stop and restart the backend. Sign in/refresh according to the app's session
   restoration flow; the local SQLite DB and keys must persist.
6. Update income/expenses with `PATCH /auth/me`; create/list an obligation; view
   dashboard, forecast and affordability results.
7. For a plan, review its persisted installment schedule. If notification/payment
   tracking is enabled in a separate local test configuration, list one payment
   occurrence, mark it paid, verify totals update, undo it, and verify totals
   restore. Default local setup keeps notification integration disabled.
8. Log out and verify the revoked access token and latest refresh token both return 401. Do not paste
   passwords, tokens, retry keys or request headers into command history/logs.

This is a manual local smoke sequence, not proof of production readiness, push
delivery, Windows execution, real-device compatibility, or store approval.

### Backend-only V2 smoke commands

Run these in a separate PowerShell terminal while the backend is on loopback.
Enter a new disposable email and a disposable password of at least eight
characters. Keep this terminal open during the restart. Avoid verbose HTTP
tracing or printing the token variables.

```powershell
$base = 'http://127.0.0.1:8000'
$email = Read-Host 'Disposable test email'
$passwordInput = Read-Host 'Disposable test password' -AsSecureString
$credential = [pscredential]::new($email, $passwordInput)
$login = @{ email = $email; password = $credential.GetNetworkCredential().Password }
$registration = @{ name = 'Local smoke'; email = $email; password = $login.password }
$null = Invoke-RestMethod "$base/auth/register" -Method Post -ContentType application/json -Body ($registration | ConvertTo-Json)
$session = Invoke-RestMethod "$base/auth/sessions" -Method Post -ContentType application/json -Body ($login | ConvertTo-Json)
Remove-Variable login, registration, credential, passwordInput
$headers = @{ Authorization = "Bearer $($session.access_token)" }
$profile = Invoke-RestMethod "$base/auth/me" -Headers $headers
if ($profile.email -ne $email) { throw 'Unexpected profile owner.' }
```

Stop the API with Ctrl+C in its own terminal, then start it again with
`.\scripts\start-local-windows.ps1`. Run the following in the earlier smoke
terminal. Refresh success after restart confirms the session survived.

```powershell
$python = '.\.venv\Scripts\python.exe'
$retry = & $python -I -c 'import secrets; print(secrets.token_urlsafe(32))'
$session = Invoke-RestMethod "$base/auth/refresh" -Method Post -ContentType application/json -Body (@{
    refresh_token = $session.refresh_token; retry_key = $retry
} | ConvertTo-Json)
$headers = @{ Authorization = "Bearer $($session.access_token)" }
$null = Invoke-RestMethod "$base/auth/me" -Headers $headers
$null = Invoke-RestMethod "$base/auth/logout" -Method Post -Headers $headers
try {
    $null = Invoke-RestMethod "$base/auth/me" -Headers $headers -ErrorAction Stop
    throw 'Revoked access token still worked.'
} catch {
    if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 401) { throw }
}
try {
    $null = Invoke-RestMethod "$base/auth/refresh" -Method Post -ContentType application/json -Body (@{
        refresh_token = $session.refresh_token; retry_key = (& $python -I -c 'import secrets; print(secrets.token_urlsafe(32))')
    } | ConvertTo-Json) -ErrorAction Stop
    throw 'Revoked refresh token still worked.'
} catch {
    if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 401) { throw }
}
Remove-Variable session, headers, retry, profile
```

## Troubleshooting

- **JWT missing/weak:** run setup. It creates a key only if the setting is
  absent. For a present invalid/empty key, inspect the name locally and correct
  it with a password manager/random generator; do not paste it to support. Keep
  a valid existing key unchanged.
- **Session receipt key error:** `SESSION_AUTH_ENABLED=true` requires a distinct
  random 32-byte base64 key. Do not reuse JWT or rate-limit material.
- **Database error/pending migrations:** verify the backend working directory,
  `DATABASE_URL`, local SQLite file and Alembic head. Inspect/backup before
  `-ApplyMigrations`; never point this helper at a shared or production DB.
- **Redis unavailable:** local memory limiter does not need Redis. If Redis is
  deliberately selected, validate its service, URL, password, TLS/CIDR settings,
  and separate HMAC key. Do not silently switch production to memory.
- **Port in use:** stop the other development server or choose an available port
  with `-Port <port>` and update the phone URL/firewall rule accordingly.
- **Phone cannot connect:** use `-ListenOnLan`, select the current Wi-Fi IPv4,
  check same Wi-Fi/no client isolation, Private firewall profile and narrow
  LocalSubnet permission. `/health` only tests reachability.
- **Expo API connection fails:** set `EXPO_PUBLIC_API_URL` in the Expo terminal,
  restart Expo, and use the PC's current Wi-Fi IPv4 with port 8000. Do not use a
  stale IP or a simulator loopback address on a physical phone.
- **PowerShell execution policy:** use the process-only command above; do not
  change `LocalMachine` or `CurrentUser` policy for this setup.

## Security boundary

`.env.local` and `dabbarha.db` are local ignored development data. Keep them
private and out of support logs/backups shared with others. Do not use real
financial data or credentials. The helper has no production migration mode and
never runs a downgrade, reset, account cleanup or provider call. Remove local
test accounts through the app's account-deletion flow when finished. The actual
Windows/PowerShell run remains unverified until tested on Jomana's Windows host.


## Mac external verification

From Mac Terminal run the following using the previously provisioned tools.
The runner prints the path of its private log and requires network access for
`pip-audit`. It uses the existing Phase 2g.3 checks and starts real disposable
PostgreSQL and Redis through the test fixtures.

```bash
cd ~/Projects/dabbarha-backend && bash scripts/run-phase-2h2-verification.sh
```

Expect 44 matching pins, 44 Linux lock hashes, clean dependency and Git/secret
checks, 21 passing Windows helper cases, seven passing focused integration cases
and 756 full-suite passes with
zero failures, errors, skips, deselections or expected failures. The existing
Starlette/httpx warning is acceptable. Send the log path and Windows smoke
results for review, including the frontend commit used.
