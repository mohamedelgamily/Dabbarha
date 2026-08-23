# Dabbarha / دبّرها Progress Log

## Current Status

Project: Dabbarha / دبّرها

Current phase: Phase 1b.2 - User + Obligation Models and First Alembic Migration

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

## What Was Intentionally NOT Built Yet

- Authentication
- Password hashing
- CRUD endpoints or routes
- Forecasting
- Dashboard endpoints
- Affordability endpoints
- Extra API endpoints
- Additional infrastructure or abstractions

## Next Planned Step

Phase 1c - API layer planning

## Design Decision

The backend starts as a modular FastAPI API. Forecasting logic will later live in one shared module.

Alembic is being introduced from the beginning so schema changes are tracked through migrations rather than manual database edits.

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

## Future Updates

Use this section to record progress in later phases.
