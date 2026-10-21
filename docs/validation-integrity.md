# Phase 2b.4 — Input validation and database integrity

Verified on mohamed/backend at HEAD `2b13e37c4ed6800f69915a97416d97b25bf0dd12`, preserving the uncommitted Phase 2b.1–3 baseline. No migrations, persistent records, real environment values, dependency files or frontend files were changed. No staging or commits.

## Request policy

Limits live in `app/schemas/validation.py`. Request-only constraints preserve legacy response serialization.

| Input | Accepted values / reason |
| --- | --- |
| Monetary amounts, income, fixed expenses | Finite Decimal, 0 through 9,999,999,999.99, up to 12 significant digits and two fractional digits; matches existing Numeric(12,2). Numeric strings and JSON numbers accepted. Insignificant trailing zeros are accepted. No rounding to rescue an invalid request. |
| Installment and affordability term | Integer 1–1,200 months, explicitly approved by the user. No truncation. Numeric strings and integral numeric values retain existing parsing; booleans rejected. |
| Forecast | Existing 1–60 months. Mid-month start dates still normalize through the unchanged engine. |
| Calendar | Valid Python dates, years 1–9999. Last included month must be representable for obligations/forecast. Affordability also needs its exclusive end month representable because the existing evaluator calculates it. |
| Required text | Trim before length validation; name/provider 1–120, item 1–160, category 1–80 characters. Arabic and English Unicode preserved. |
| Currency | Existing policy retained: trim, uppercase, 1–3 characters; no new currency allowlist. |
| Partial updates | Omitted fields remain unchanged; explicit null rejected. Obligation updates validate the complete merged state before mutating the ORM object. |
| Registration/profile | Name/email/password JSON contract unchanged; passwords are not trimmed or given new length rules. Financial profile remains optional, with existing zero/EGP defaults. |

No new relationship between total price, monthly payment and term was imposed. Due day 31 remains accepted even for a February start; no new payment-day business policy was introduced.

## Before and after

| Verified gap | Before | After |
| --- | --- | --- |
| Explicit null obligation update | Can reach non-nullable columns and fail as a server error | 422 before mutation |
| Whitespace text | Length checked before trimming; empty stored values possible | Trim first, reject empty with 422 |
| Precision/range | SQLite can round extra decimals or accept values outside declared PostgreSQL precision | Request rejects overprecision/oversize with 422 |
| Duration | No upper bound | User-approved 1–1,200 cap; extreme integers produce 422 |
| Extreme dates | Calendar arithmetic can raise ValueError/500 | Bounds checked before calculations; 422 |
| Raw NaN/Infinity JSON | Default validation error echo can itself fail JSON serialization | Safe 422; nine regressions reproduced before handler fix and pass afterward |
| Partial date/term changes | Fields validated independently | Complete merged state checked before assignment |
| Profile write failure | No explicit rollback | Rollback on failure; next operation succeeds |
| Database failure response | Unhandled driver errors | Integrity conflicts return safe 409; other SQLAlchemy failures return generic 500, without SQL/parameters/driver text |

Validation errors retain `detail` arrays containing `type`, `loc`, `msg`; raw rejected `input`, context and documentation URLs are omitted. Existing explicit query-policy errors retain their detail strings. The read-only frontend review confirms its Axios client understands these formats.

## SQLite and transaction behavior

`create_app_engine` installs a connection listener on the application engine: every new SQLite connection enables foreign keys before use, including after pool disposal/reconnection. The listener handles sqlite3 autocommit modes. Existing FK/check/not-null constraints and database ON DELETE CASCADE now apply on application connections. Disposable database tests prove rejection of orphan obligations, rollback/recovery and database cascade. This is not an automatic repair of historical orphans. External SQLite clients still need their own FK policy. No new database constraints or migrations were added.

Mutation endpoints roll back failed writes; the request session dependency explicitly rolls back on exceptions and always closes. New tests inject both real failed flushes (pending-rollback state) and operational failures for create/update/delete/profile, check safe errors and unchanged records, then successfully reuse the session. Read/modify/delete ownership conditions still constrain record ID and owner ID. ORM queries use bound parameters; SQL-like provider text roundtrips without execution.

The existing commit-then-refresh pattern remains. A connection failure after a successful commit can still leave the client uncertain whether a write succeeded; retry/idempotency design is outside this batch. Concurrent updates retain the existing last-write-wins behavior.

SQLite Numeric is not fixed-point decimal enforcement: direct ORM/SQL writes can bypass request precision/length/term rules, and SQLite may store floating-point representations. PostgreSQL enforces Numeric(12,2) precision but may round extra fractional digits; API validation rejects them first on either backend. PostgreSQL behavior, drivers, deployment and approved schema changes are deferred; no claim of PostgreSQL runtime verification is made.

## Compatibility and remaining risks

Valid frontend keys, money strings/numbers, Decimal responses, status/source values, JSON login, HS256 tokens, 60-minute default expiration, Argon2id passwords, optional profile and financial formulas remain unchanged. Frontend form validation does not yet enforce the new monetary and duration bounds; such submissions receive 422. No mobile build/runtime test was performed and no frontend files were edited.

Legacy records remain readable and are never shortened, rounded or rewritten automatically. An update to an out-of-policy legacy record requires submitting a corrected complete merged state, even when only its text was intended to change. A regression proves a 1,201-month record remains readable/unchanged after a rejected text update. No persistent data scan was run, so prevalence of legacy violations is unknown. Existing zero profile defaults still cannot distinguish an unset profile from explicit zero income. Very large request bodies, rate limiting, concurrent-write controls, PostgreSQL deployment and remaining broader audit items are outside this phase. The 1,200-month cap bounds assessment months but does not bound the number of a user's obligations.

## Verification

Clean Phase 2b.3 isolated environment, CPython 3.12.0 on macOS Intel; original backend `.venv` preserved. Production requires a supported security-patched Python 3.12 release on Ubuntu 24.04 x86_64 and separate PostgreSQL verification.

Command (run from backend): `PYTHONDONTWRITEBYTECODE=1 <clean-verify-venv>/bin/python -m pytest -q -p no:cacheprovider`

**433 passed, 1 warning in 28.68s.** Includes 307 existing tests and 126 new validation/integrity cases. The warning is the existing Starlette TestClient/httpx deprecation; no package upgrade was made. Tests include authentication, optional profile, all financial calculations, 1/1,200/1,201/extreme duration inputs, money bounds, nulls, Unicode, invalid dates, overflow, partial updates, rollback/recovery, foreign keys and cross-user isolation. `pip check`: no broken requirements. Dependency vulnerability scanning was not rerun in this phase; dependency files remain byte-identical to the prior verified phase. `git diff --check`: passed.

## Files in this phase

- `app/schemas/validation.py`: shared monetary, duration, text and calendar policy.
- `app/schemas/auth.py`: trimmed name and financial-profile money validation.
- `app/schemas/obligation.py`: request limits, null rejection and calendar validation.
- `app/schemas/affordability.py`: shared limits and exclusive-end calendar guard.
- `app/api/routes/obligations.py`: merged-state validation before ORM mutation.
- `app/api/routes/forecast.py`: shared forecast limit and overflow rejection.
- `app/api/routes/auth.py`: profile write rollback.
- `app/api/deps.py`: rollback on request exceptions, close in finally.
- `app/db/database.py`: application engine factory with per-connection SQLite FK enforcement.
- `app/main.py`: safe request-validation and database exception responses, preserving prior environment/docs policy and chatbot removal.
- `tests/test_validation_integrity.py`: 126 new regression cases.
- `docs/validation-integrity.md`: this policy, verification and limitations.
- `PROGRESS.md`: verified Phase 2b.4 entry.
