# Dabbarha / دبّرها Progress Log

## Current Status

Project: Dabbarha / دبّرها

Current phase: Phase 1c.3 - Login + JWT

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

## What Was Intentionally NOT Built Yet

- `/auth/me` endpoint
- Refresh tokens
- Authentication middleware/dependencies for protected routes
- Full authentication flow
- CRUD endpoints or routes
- Forecasting
- Dashboard endpoints
- Affordability endpoints
- Extra API endpoints
- Additional infrastructure or abstractions

## Next Planned Step

Phase 1c.4 — Protected /auth/me endpoint

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
- Ran `pytest tests/test_auth.py -q -p no:cacheprovider`: 29 passed in 2.21s.
- Ran `pytest -q`: 51 passed in 3.39s.
- Verified `GET /health` continues to return `{"status": "ok"}`.
- Verified no new Alembic revisions were generated.
- Verified developer SQLite database `dabbarha.db` was not modified during testing.

## Future Updates

Use this section to record progress in later phases.
