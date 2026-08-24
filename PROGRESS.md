# Dabbarha / دبّرها Progress Log

## Current Status

Project: Dabbarha / دبّرها

Current phase: Phase 1d.2 - Create Obligation (POST /obligations)

Status: completed after verification

## What Was Built

### Phase 1a - Skeleton + Health Check

- Created a minimal FastAPI backend application.
- Added exactly one application endpoint: `GET /health`.
- Configured `/health` to return `{"status": "ok"}`.
- Added minimal Python runtime dependencies for FastAPI and Uvicorn.
- Added baseline ignored files for local environments, Python cache output, environment files, macOS metadata, and pytest cache.
- Added an example environment configuration file with no real secrets.

### Phase 1b.1 - Database Foundation

- Added SQLAlchemy and Alembic dependencies.
- Created a small database configuration module that reads `DATABASE_URL` from the environment.
- Added a local development fallback database URL: `sqlite:///./dabbarha.db`.
- Created the SQLAlchemy database engine.
- Configured SQLite connection arguments for local development.
- Created the SQLAlchemy session factory.
- Created a declarative `Base` for future SQLAlchemy models.
- Initialized Alembic.
- Configured Alembic to use the application's database configuration.
- Configured Alembic `target_metadata` from the application's `Base`.
- Updated environment and ignore files for the local SQLite database.

### Phase 1b.2 - User + Obligation Models and First Alembic Migration

- Created the `User` SQLAlchemy model mapped to the `users` table.
- Created the `Obligation` SQLAlchemy model mapped to the `obligations` table.
- Added a one-to-many `User.obligations` relationship and matching `Obligation.user` relationship.
- Added a required foreign key from `obligations.user_id` to `users.id`.
- Added database-level check constraints for non-negative money values.
- Added database-level check constraints for obligation term length and due day range.
- Added database-level check constraints for allowed obligation status and source values.
- Updated Alembic to import application models before autogeneration.
- Generated the first Alembic migration to create `users` and `obligations`.

### Phase 1b.3 - Automated Model Tests

- Added pytest as the project test runner.
- Added automated SQLAlchemy model tests.
- Tested `User` persistence.
- Tested `Obligation` persistence.
- Tested `User` and `Obligation` relationships.
- Tested financial database constraints.
- Tested status and source database constraints.
- Tested foreign-key enforcement.
- Tested email uniqueness.
- Used an isolated in-memory SQLite test database.

### Phase 1c.1 - Authentication Security Foundation

- Added password hashing with Argon2 through pwdlib.
- Added password verification.
- Added JWT access-token creation.
- Added JWT decoding and validation.
- Added authentication configuration.
- Added security utility tests.
- Created the minimal future authentication package structure without endpoints.

### Phase 1c.2 - Registration Endpoint

- Created `UserCreate` and `UserResponse` Pydantic schemas in `app/schemas/auth.py`.
- Created database session dependency `get_db` in `app/api/deps.py`.
- Implemented `POST /auth/register` in `app/api/routes/auth.py`.
- Added duplicate email conflict handling returning HTTP 409.
- Implemented password hashing during registration using Argon2.
- Ensured safe user responses excluding `password` and `password_hash`.
- Registered the auth router in `app/main.py` under `/auth`.
- Added comprehensive automated API registration tests in `tests/test_auth.py`.

### Phase 1c.3 — Login + JWT

Built:
- `UserLogin` and `Token` schemas in `app/schemas/auth.py`
- `POST /auth/login` endpoint in `app/api/routes/auth.py`
- Credential verification using existing Argon2 utility (`verify_password`)
- Generic authentication failure returning HTTP 401 Unauthorized with `WWW-Authenticate: Bearer`
- JWT access token issuance via `create_access_token`
- JWT claims containing strictly subject (`sub`) as string user ID and expiration (`exp`)
- Comprehensive login API test suite in `tests/test_auth.py`

Security:
- Existing Argon2 password hashing reused
- Existing JWT implementation reused
- JWT contains only authentication claims (`sub`, `exp`)
- No financial, email, name, or password data stored in JWT
- Generic invalid-credential response (`"Invalid email or password"`) prevents account enumeration

Testing:
- 51 automated tests passing across models, security utilities, and authentication routes (`pytest -q`)

Next Planned Step:
Phase 1c.4 — Protected /auth/me endpoint

### Phase 1c.4 — Protected /auth/me Endpoint

Built:
- Reusable `get_current_user` dependency in `app/api/deps.py` extracting and validating Bearer tokens via `OAuth2PasswordBearer` and `decode_access_token`
- `GET /auth/me` endpoint in `app/api/routes/auth.py` protected by `get_current_user` dependency
- Safe `UserResponse` serialization returning public profile fields (`id`, `name`, `email`, `monthly_income`, `fixed_expenses`, `currency`, `created_at`) and omitting `password` / `password_hash`
- Full test coverage in `tests/test_auth.py` for successful profile retrieval, missing Authorization header, malformed/tampered JWT, expired JWT, nonexistent user referenced in JWT, non-integer subject payload, and credential confidentiality

Security:
- Reusable `get_current_user` dependency enforces authentication before handler invocation
- Invalid, expired, malformed, or nonexistent user credentials reject with standard `HTTP 401 Unauthorized` and `WWW-Authenticate: Bearer` header
- No sensitive authentication secrets (`password`, `password_hash`) are exposed by the endpoint or dependency
- No database schema changes or migrations introduced

Testing:
- 58 automated tests passing across models, security utilities, and authentication routes (`pytest -q`)

Next Planned Step:
Phase 1d — Obligation CRUD

### Phase 1d.1 — Obligation API Foundation & Schemas

Built:
- `ObligationCreate` and `ObligationResponse` Pydantic schemas in `app/schemas/obligation.py`
- Obligation router foundation in `app/api/routes/obligations.py` registered under `/obligations` prefix in `app/main.py`
- Strict Pydantic schema validations matching database-level constraints:
  - `total_amount >= 0`
  - `monthly_installment_amount >= 0`
  - `term_months > 0`
  - `due_day_of_month` between 1 and 31
  - `status` restricted to allowed enum literals (`active`, `completed`, `late`, `defaulted`)
  - `source` restricted to allowed enum literals (`manual_entry`, `chatbot_entry`)
- Security enforcement preventing client-supplied `user_id` in `ObligationCreate` (`extra="forbid"`)
- Comprehensive schema validation test suite in `tests/test_obligations.py`

Security:
- `user_id` is excluded from `ObligationCreate` and forbidden in request payloads, ensuring user ownership is solely assigned by authenticated backend dependencies in upcoming CRUD handlers
- Safe ORM response serialization via `ObligationResponse` compatible with SQLAlchemy models
- No database schema changes or Alembic migrations required

Testing:
- 86 automated tests passing across models, security utilities, authentication routes, and obligation schemas (`pytest -q`)

Next Planned Step:
Phase 1d.2 — Create Obligation (POST /obligations)

### Phase 1d.2 — Create Obligation Endpoint

Built:
- `POST /obligations` endpoint in `app/api/routes/obligations.py`
- Protected by `get_current_user` dependency to enforce authentication
- Input validation via `ObligationCreate` schema
- Server-side assignment of `user_id` from the authenticated user (`current_user.id`)
- Persistence to database via `get_db` session
- Successful response returns `HTTP 201 Created` with serialized `ObligationResponse`
- Comprehensive API integration test suite in `tests/test_obligations.py` covering authenticated creation, unauthenticated requests (401), invalid/expired tokens (401), user_id spoofing prevention (422), schema validation failures (422), missing required fields (422), and multi-user isolation verification

Security:
- Obligation ownership is strictly bound to the authenticated user ID extracted from JWT token
- Extra fields including `user_id` are forbidden on the request body (`extra="forbid"`)
- Database isolation verified: obligations are inaccessible and unlinked to other user accounts
- No database schema modifications or Alembic migrations required

Testing:
- 108 automated tests passing across models, security utilities, authentication routes, and obligation CRUD (`pytest -q`)

Next Planned Step:
Phase 1d.3 — List & Read Obligations (GET /obligations, GET /obligations/{id})

## What Was Intentionally NOT Built Yet

- GET /obligations
- GET /obligations/{id}
- PATCH /obligations/{id}
- DELETE /obligations/{id}
- Refresh tokens
- Full logout / token invalidation
- Forecasting
- Dashboard endpoints
- Affordability endpoints
- Extra API endpoints
- Additional infrastructure or abstractions

## Next Planned Step

Phase 1d.3 — List & Read Obligations (GET /obligations, GET /obligations/{id})

## Design Decision

The backend starts as a modular FastAPI API. Forecasting logic will later live in one shared module.

Alembic is being introduced from the beginning so schema changes are tracked through migrations rather than manual database edits.

Application tests use an isolated test database and never modify the developer's local `dabbarha.db`.

Argon2id is used for password hashing through pwdlib.

PyJWT is used for JWT handling.

JWT uses HS256 for local development.

JWT contains only user identity and expiration information.

Access tokens initially expire after 60 minutes.

Refresh tokens are intentionally deferred.

No plaintext passwords are stored.

No financial information is stored in JWTs.

User registration accepts input via `UserCreate` and returns sanitized `UserResponse`.

`password_hash` is never returned by the API.

Registration does not issue JWTs directly.

Login uses a standard JSON payload (`UserLogin`) returning a `Token` model with `access_token` and `token_type = "bearer"`.

Email is normalized (trimmed and lowercased) before user lookup to match registration behavior.

Authentication failures for nonexistent users and wrong passwords return identical HTTP 401 responses with `WWW-Authenticate: Bearer` to protect against user enumeration.

JWT payload is restricted strictly to subject (`sub`) representing user ID as a string and expiration timestamp (`exp`).

`get_current_user` is implemented as a reusable FastAPI dependency combining `OAuth2PasswordBearer` and existing JWT/database validation logic.

Authentication failure in `get_current_user` returns `HTTP 401 Unauthorized` with `WWW-Authenticate: Bearer` header across all failure modes (missing token, malformed signature, expired token, invalid subject claim, nonexistent user record).

`ObligationCreate` forbids extra fields including `user_id` so clients cannot spoof obligation ownership. The server associates obligations to the authenticated user retrieved by `get_current_user`.

Obligation schemas use `Decimal` for precise financial values, `date` for start dates, and `datetime` for timestamps.

`POST /obligations` assigns `user_id` from `current_user.id` on the server. The client has no ability to set or override the owner ID.

Creation returns `HTTP 201 Created` with `ObligationResponse`.

## Verification

- Imported the application database configuration.
- Created a SQLAlchemy engine from the configured database URL.
- Confirmed Alembic can load its migration environment.
- Confirmed no Alembic revisions were generated because no application models exist yet.
- Imported both SQLAlchemy models.
- Confirmed Alembic can discover both model tables through `Base.metadata`.
- Generated the initial Alembic migration through autogenerate.
- Ran Alembic upgrade against a temporary SQLite database.
- Ran Alembic downgrade against the same temporary SQLite database.
- Ran `pytest tests/test_models.py -q -p no:cacheprovider`: 13 passed in 0.53s.
- Ran `pytest tests/test_security.py -q -p no:cacheprovider`: 9 passed in 0.44s.
- Ran `pytest tests/test_auth.py -q -p no:cacheprovider`: 36 passed in 2.50s.
- Ran `pytest tests/test_obligations.py -q -p no:cacheprovider`: 50 passed in 2.55s.
- Ran `pytest -q`: 108 passed in 6.13s.
- Verified `GET /health` continues to return `{"status": "ok"}`.
- Verified no new Alembic revisions were generated.
- Verified developer SQLite database `dabbarha.db` was not modified during testing.

## Future Updates

Use this section to record progress in later phases.
