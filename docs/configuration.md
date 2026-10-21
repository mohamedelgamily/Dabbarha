# Environment and JWT configuration

Phase 2b.1 removes the public development JWT signing-key fallback. The application
validates configuration when `app.core.config` is imported, before it can serve
requests. Development, test and production all require an explicit signing key.
No key is generated, normalized, rotated, persisted or logged by the application.

## Loading mechanism

The application reads **only the process environment**. It never discovers `.env`
files or searches parent directories. Uvicorn's existing `--env-file` option loads
one explicitly named file using its installed python-dotenv dependency **before**
importing the app. This is the supported local mechanism; no packages were added.
Existing process variables take precedence over file values. An explicitly empty
process variable also takes precedence and will fail validation; unset it if the
selected file is intended to supply it. Do not `source` an untrusted dotenv file.

Plain `python`, Alembic and other entrypoints do not load dotenv files. Supply the
same explicit process environment through your trusted launcher/secret manager.
Tests verify Uvicorn's actual file loader, both precedence cases and the absence
of automatic loading. Settings are a startup snapshot; restart to apply changes.
Never run production with `--reload` or trust a development template as deployment
configuration.

## Local development

1. Create an ignored `.env.local` from `.env.example` and restrict access to its
   owner. This does not require changing an existing `.env` file.
2. Set `APP_ENV=development` explicitly and fill `JWT_SECRET_KEY` using a password
   manager or a cryptographic random generator. Prefer 48 random bytes encoded as
   URL-safe text. Keep that same value across restarts to preserve valid sessions.
   Do not send it in chat, terminal output, screenshots or logs.
3. Start from the backend repository root (also required by the current relative
   SQLite database path):

```sh
.venv/bin/uvicorn app.main:app --env-file /absolute/path/to/.env.local
```

Placeholder-only example; the JWT placeholder is deliberately rejected:

```dotenv
APP_ENV=development
JWT_SECRET_KEY=<set-secure-random-secret-locally>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
API_DOCS_ENABLED=true
```

v1.0 has no AI provider or chatbot configuration. `/chat` is not registered and
returns 404. Existing provider values in local/deployment environments are ignored;
this phase does not read, rewrite, print or rotate them. Remove them from deployment
secret management only through a separate approved operational change.

## Validated policy

| Setting | Default and validation |
|---|---|
| `APP_ENV` | `production`; only development, test, production accepted |
| `JWT_SECRET_KEY` | Required; at least 32 UTF-8 bytes; rejects empty, documented placeholders, template brackets, low character diversity, repeated/obvious sequential values and surrounding whitespace/control characters |
| `JWT_ALGORITHM` | `HS256` only; same algorithm as the established contract |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 60; must be a positive integer; explicit positive existing overrides retained |
| `API_DOCS_ENABLED` | true in development/test, false in production; explicit boolean override allowed |
| `DATABASE_URL` | Existing SQLite default retained; explicit empty value rejected |

Secret heuristics cannot prove entropy. Generate random secret material rather
than crafting a value merely to pass validation. Allowed secret bytes are used
unchanged; the app never trims or rewrites a configured secret. Error messages
identify invalid fields without including supplied values; settings repr omits
values. Do not dump settings/environment objects through external tooling.

`API_DOCS_ENABLED` governs Swagger, ReDoc, OpenAPI JSON and Swagger's OAuth redirect.
If explicitly enabled in production, those documentation routes are public.
`/health` remains the same public liveness response; it is not readiness or a
provider probe. Business-route authentication remains unchanged. Debug is false.

## Production rollout and session compatibility

Inject `APP_ENV=production` from deployment configuration, alongside the existing
secure HS256 key and other required process variables. Omit `API_DOCS_ENABLED`
or set it false. Do not deploy by copying the development
mode/docs values from the example wholesale. Use the deployment's trusted secret
manager; no automatic environment file is needed.

A missing, empty, sample or weak key now prevents startup in every mode. This is
intentional. **Do not replace an existing deployed key just to make startup pass.**
If it is rejected, schedule a separately approved key remediation: replacing it
will invalidate tokens signed with the previous key, including potentially
forged tokens if the old public fallback was used. This batch performs no such
rotation or session invalidation. There is no compatibility mode accepting the
old public key.

With the same valid explicit key, existing HS256 tokens containing `sub` and `exp`
remain valid until their existing expiry. Login/registration JSON, token response
`{access_token, token_type}`, Argon2id hashes and optional financial profile are
unchanged. Other algorithms now fail configuration rather than silently changing
the deployment's signing contract; an alternate algorithm requires a separate
approved migration.

## Phase 2d notification activation

Notification settings default to disabled, so API startup does not start a worker
or call Expo. Enable `NOTIFICATIONS_ENABLED=true` only after applying the additive
Phase 2d migration and setting `SESSION_AUTH_ENABLED=true`; push tokens must be
bound to revocable device sessions. `PUSH_TOKEN_ENCRYPTION_KEY` must be a separate
random 32-byte key encoded as base64. Keep it in the deployment secret manager;
the application never generates or prints it. `NOTIFICATION_DELIVERY_ENABLED`
separately controls provider delivery. Real Expo delivery is production-only;
development delivery requires an explicit mock provider. `EXPO_PUSH_ACCESS_TOKEN`
is optional and should be configured as a secret only if the Expo project uses it.

Start the database-backed worker as a separately supervised service with
`python -m app.commands.notification_worker`. No API process starts it. See
`payment-reminders.md` for settings, retry limits and worker operations, and
`frontend-notifications-handoff.md` for the required Expo/device-session client
work. Keep notifications disabled until that frontend rollout is ready.

Phase 2b.2 deliberately removes `/chat`; old mobile versions must remove or hide
the route and shortcuts before v1.0 release. There is no outage or mock fallback.
See `frontend-v1-handoff.md` and `conversation-retirement.md` for compatibility and
archival database policy. The legacy `chatbot_entry` obligation-source value remains
supported as provenance metadata for existing records, not as an AI feature.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

`tests/conftest.py` configures an explicit test environment, an ephemeral signing
key and an in-memory DB before application import.
It does not read local `.env` files or alter parent-shell/file values. Test token
values are deliberately different from deployed credentials. Configuration/startup
subprocesses use synthetic keys and controlled environments. No external API call or persistent database operation is part of these tests.
Release-boundary tests replay existing migrations only on disposable in-memory
SQLite and retain synthetic archival rows while exercising financial operations.

## Phase 2b.5 request protection

Application startup now also validates `APISecuritySettings`: production requires
private shared Redis and a separate `RATE_LIMIT_HMAC_KEY`. See `api-security.md`
for the complete settings table, safe failure behavior and inactive deployment
templates. Development/test defaults to bounded local counters. The same explicit
process-environment / Uvicorn `--env-file` loading policy applies; no real dotenv
file is rewritten or discovered automatically.
