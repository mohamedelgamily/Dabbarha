# Dabbarha / دبّرها Progress Log

## Current Status

Project: Dabbarha / دبّرها

Current phase: Phase 2e — Account Deletion & Privacy

Status: implementation and disposable local SQLite/PostgreSQL/Redis verification complete; production deployment and external deletion-request operations remain unverified

The current v1.0 backend has no AI/chat endpoint, provider, tools, memory or RAG. Earlier AI implementation and Phase 2b.1 entries below are historical records; Phase 2b.2 supersedes their feature-specific behavior. JWT/environment security hardening remains active.

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

### Phase 1d.3 — List & Read Obligations Endpoints

Built:
- `GET /obligations` endpoint in `app/api/routes/obligations.py`
  - Protected by `get_current_user` dependency to enforce authentication
  - Returns only obligations belonging to the authenticated user (`Obligation.user_id == current_user.id`)
  - Returns an empty list when the user has no obligations
  - Response model is `list[ObligationResponse]`
- `GET /obligations/{id}` endpoint in `app/api/routes/obligations.py`
  - Protected by `get_current_user` dependency to enforce authentication
  - Returns the obligation only if it belongs to the authenticated user
  - Returns `HTTP 404 Not Found` with generic detail `"Obligation not found"` when the obligation does not belong to the user or does not exist, preventing information leakage
  - Response model is `ObligationResponse`
- Comprehensive API integration test suite in `tests/test_obligations.py` covering:
  - Authenticated user can list their own obligations
  - Empty list when user has no obligations
  - Multiple obligations returned correctly
  - User A cannot see User B's obligations via list endpoint
  - User A cannot retrieve User B's obligation by ID
  - Missing authentication returns 401
  - Invalid JWT returns 401
  - Expired JWT returns 401
  - Nonexistent obligation returns 404
  - Response schema correctness

Security:
- Obligation ownership is enforced at the query level by filtering on `current_user.id`
- `user_id` is never accepted from the client in GET endpoints
- 404 responses use a generic message to avoid leaking whether an obligation exists but belongs to another user
- No database schema modifications or Alembic migrations required

Testing:
- 120 automated tests passing across models, security utilities, authentication routes, and obligation CRUD (`pytest -q`)

Next Planned Step:
Phase 1d.4 — Update & Delete Obligations (PATCH /obligations/{id}, DELETE /obligations/{id})

### Phase 1d.4 — Update & Delete Obligations Endpoints

Built:
- `PATCH /obligations/{id}` endpoint in `app/api/routes/obligations.py`
  - Protected by `get_current_user` dependency to enforce authentication
  - Allows partial updates through `ObligationUpdate`
  - Updates only obligations owned by the authenticated user
  - Returns `HTTP 404 Not Found` with generic detail `"Obligation not found"` for nonexistent or cross-user obligations
  - Returns the updated obligation as `ObligationResponse`
- `DELETE /obligations/{id}` endpoint in `app/api/routes/obligations.py`
  - Protected by `get_current_user` dependency to enforce authentication
  - Deletes only obligations owned by the authenticated user
  - Returns `HTTP 204 No Content` on successful deletion
  - Returns generic `HTTP 404 Not Found` for nonexistent or cross-user obligations
- Extended obligation API tests in `tests/test_obligations.py` for successful updates, partial updates, validation failures, authenticated ownership enforcement, successful deletion, repeated/nonexistent deletion, and cross-user isolation.

Security:
- Update and delete operations preserve the existing ownership boundary by filtering obligations by both ID and authenticated user.
- Cross-user update/delete attempts return the same generic 404 response as nonexistent obligations.
- No database schema modifications or Alembic migrations required.

Testing:
- Obligation CRUD tests and full suite passed after implementation.

Next Planned Step:
Phase 1e.1 — Pure Forecast Module

### Phase 1e.1 — Pure Forecast Module

Built:
- Added reusable pure forecast logic in `app/core/forecast.py`.
- Forecasting accepts monthly income, fixed expenses, a collection of obligation-like objects, a forecast start month, and a month count.
- Produces monthly forecast rows containing:
  - income
  - fixed expenses
  - active obligation payments
  - projected buffer
  - negative-buffer flag
- Kept forecasting independent of FastAPI, HTTP routing, database sessions, and SQLAlchemy queries.
- Designed the module around the existing `Obligation` model fields while using a small protocol so it can also work with compatible in-memory objects.
- Handles forecast month normalization, obligation start dates, term month windows, obligations that begin before or after the forecast period, calendar year boundaries, mid-month start dates, and payable statuses (`active`, `late`).
- Excludes non-payable statuses (`completed`, `defaulted`) from projected payments.
- Added focused unit tests in `tests/test_forecast.py`.

Testing:
- Ran `pytest -q tests/test_forecast.py`: 14 passed.
- Ran `pytest -q`: 134 passed.
- Ran `git diff --check`: passed.

Commit:
- Phase 1e.1 completed in commit `95940bd`.
- Previous checkpoint: `eb9b0cd`.

Next Planned Step:
Phase 1e.2 — Forecast API Integration

### Phase 1e.2 — Forecast API Integration

Built:
- Added protected `GET /forecast` endpoint.
- Reused `get_current_user` so only authenticated users can request forecasts.
- Loaded only obligations belonging to the authenticated user.
- Used `current_user.monthly_income` and `current_user.fixed_expenses`; clients cannot provide `user_id`, income, or fixed expenses.
- Accepted only forecast-window query inputs: `start_month` and `months`.
- Called `build_forecast()` from `app/core/forecast.py` with no forecast math duplicated in the route.
- Added typed forecast API response schemas for monthly forecast rows.
- Added focused API integration tests in `tests/test_forecast_api.py` covering authentication, user isolation, forecast results, invalid parameters, and rejection of non-window query inputs.

Security:
- Forecast data is scoped to the authenticated user at the obligation query boundary.
- The endpoint does not accept client-supplied financial profile values or owner IDs.
- No database schema modifications or Alembic migrations required.

Testing:
- Ran `pytest -q tests/test_forecast.py tests/test_forecast_api.py`: 28 passed.
- Ran `pytest -q`: 148 passed.
- Ran `git diff --check`: passed.

Commit:
- Phase 1e.2 completed in commit `f5f541c`.

Next Planned Step:
Phase 1f.1 — Dashboard Summary API

### Phase 1f.1 — Dashboard Summary API

Built:
- Added protected `GET /dashboard/summary` endpoint in `app/api/routes/dashboard.py`.
- Protected by `get_current_user` dependency to enforce authentication.
- Uses authenticated user's stored `monthly_income` and `fixed_expenses`; clients cannot provide financial values or `user_id`.
- Loads only obligations belonging to the authenticated user.
- Uses `build_forecast()` from `app/core/forecast.py` to calculate current-month obligation payments and projected buffer.
- Returns typed dashboard summary data via `DashboardSummaryResponse` schema.
- Does not accept client-supplied financial values, `user_id`, or current month.
- Added focused API integration tests in `tests/test_dashboard_api.py` covering authentication, user isolation, forecast integration, and response schema correctness.

Security:
- Dashboard data is scoped to the authenticated user.
- The endpoint does not accept client-supplied financial profile values or owner IDs.
- No database schema modifications or Alembic migrations required.

Testing:
- Ran `pytest -q`: 156 passed.
- Ran `git diff --check`: passed.

Commit:
- Phase 1f.1 completed in commit `43daae7`.

Next Planned Step:
Phase 1g.1 — Pure Affordability Engine

### Phase 1g.1 — Pure Affordability Engine

Built:
- Added pure affordability logic in `app/core/affordability.py`.
- Introduced a generic `ProposedCommitment` domain model supporting one-time/cash purchases, recurring monthly expenses, and term-based installment commitments.
- `ProposedCommitment` validates `amount >= Decimal("0.00")` and `term_months > 0` at the domain level.
- `evaluate_affordability()` reuses `build_forecast()` from `app/core/forecast.py` and overlays the proposed commitment on each projected month.
- The engine evaluates the entire commitment period; it raises `ValueError` if the forecast window does not fully cover the commitment start through its term end.
- Overall classification is determined by the worst projected buffer month:
  - Comfortable: remaining buffer >= 40% of monthly income
  - Manageable: remaining buffer >= 20% and < 40%
  - Risky: remaining buffer >= 0% and < 20% (exactly 0% is Risky)
  - Not Affordable: remaining buffer < 0%
- Borderline/risky explanation: "Possible, but your remaining buffer would be low."
- Returns a typed `AffordabilityResult` containing classification, worst projected buffer, worst buffer percentage, worst month, per-month results, and an explanation string.
- Kept independent of FastAPI, HTTP routing, database sessions, and SQLAlchemy.
- Added 20 focused unit tests in `tests/test_affordability.py` covering all classification thresholds, worst-month behavior, multi-month and one-time commitments, existing-obligation interaction, zero-income edge cases, Decimal precision, commitment period boundaries, and domain validation.

Testing:
- Ran `pytest -q tests/test_affordability.py tests/test_forecast.py`: 36 passed.
- Ran `pytest -q`: 178 passed.
- Ran `git diff --check`: passed.

Commit:
- Phase 1g.1 completed in commit `8d9718c`.

Next Planned Step:
Phase 1g.2 — Affordability API

### Phase 1g.2 — Affordability API

Built:
- Added `POST /affordability` endpoint in `app/api/routes/affordability.py`.
- Protected by `get_current_user` dependency to enforce authentication.
- Uses only the authenticated user's stored `monthly_income` and `fixed_expenses`; clients cannot provide financial values or `user_id`.
- Loads only obligations belonging to the authenticated user.
- Accepts request body with `amount` (Decimal ≥ 0), `start_date` (date), and `term_months` (int > 0) via `AffordabilityRequest` schema.
- Derives the forecast window automatically from the proposed commitment: `start_month = month_start(start_date)` and `months = term_months`.
- Calls `evaluate_affordability()` from `app/core/affordability.py` with no affordability or forecast math duplicated in the route.
- Returns typed `AffordabilityResponse` exposing classification, worst projected buffer, worst buffer percentage, worst month, explanation, and per-month results.
- Rejects unexpected query parameters with HTTP 422.
- Added 19 focused API integration tests in `tests/test_affordability_api.py` covering authentication, user isolation, financial profile enforcement, request validation, all classification outcomes, multi-month commitments, and query-parameter rejection.

Security:
- Affordability data is scoped to the authenticated user at the obligation query boundary.
- The endpoint does not accept client-supplied `user_id`, income, fixed expenses, or query parameters.
- No database schema modifications or Alembic migrations required.

Testing:
- Ran `pytest -q tests/test_affordability_api.py tests/test_affordability.py tests/test_forecast.py`: 55 passed.
- Ran `pytest -q`: 197 passed.
- Ran `git diff --check`: passed.

Commit:
- Phase 1g.2 completed in commit `b384009`.

Next Planned Step:
Phase 1h.1 — Chat Foundation

### Phase 1h.1 — Chat Foundation

Built:
- Added protected `POST /chat` endpoint in `app/api/routes/chat.py`.
- Protected by `get_current_user` dependency to enforce authentication.
- Created `ChatService` domain layer in `app/core/chat/` independent of FastAPI and SQLAlchemy.
- Added `LLMProvider` protocol and `MockLLMProvider` for this phase; no external LLM calls yet.
- Added explicit `GuardrailPolicy` with deterministic `GuardrailDecision` outcomes: `allow`, `out_of_scope`, `injection`.
- Created `UserContext` from the authenticated user identity; passed through the domain service toward future tool execution.
- Added backend-controlled tool abstraction with 7 conceptual `ToolDefinition`s (dashboard_summary, forecast, affordability, list_obligations, create_obligation, update_obligation, delete_obligation).
- Tool definitions do not expose `user_id`; execution is designed around `UserContext`.
- No Gemini/Groq integration yet.
- No RAG yet.
- No conversation persistence or memory yet.
- Added 18 focused tests in `tests/test_chat.py` covering authentication, guardrail decisions, scope handling, injection blocking, provider abstraction, user context, and tool contracts.

Security:
- Chat data is scoped to the authenticated user.
- The endpoint does not accept client-supplied `user_id` or query parameters.
- No database schema modifications or Alembic migrations required.

Testing:
- Ran `pytest -q tests/test_chat.py`: 18 passed.
- Ran `pytest -q`: 215 passed.
- Ran `git diff --check`: passed.

Commit:
- Phase 1h.1 completed in commit `0104706`.

Next Planned Step:
Phase 1h.2 — Gemini Integration

### Phase 1h.2 — Gemini Integration

Built:
- Added `GeminiProvider` implementing the existing `LLMProvider` protocol in `app/core/chat/provider.py`.
- Uses the current Google GenAI SDK (`google-genai`) with `genai.Client(api_key=...)` architecture.
- Reads `GEMINI_API_KEY` from the environment via `app/core/config.py`; never hardcoded, logged, exposed, returned, or committed.
- Model name is configurable through `GEMINI_MODEL` environment variable (default: `gemini-3.7-flash`).
- Converts domain `ChatMessage` representation into Gemini request format inside `GeminiProvider`.
- Converts Gemini response into the existing domain `ChatResponse` shape.
- Passes tool definitions through the provider abstraction in a format compatible with future Gemini function/tool calling.
- Does NOT execute tools in this phase.
- `MockLLMProvider` retained for deterministic tests.
- No Groq integration yet.
- No RAG yet.
- No conversation persistence or memory yet.
- Added 9 focused tests in `tests/test_gemini_provider.py` covering initialization, missing API key, response mapping, tool definitions, error handling, API key secrecy, and MockLLMProvider continuity.

Security:
- Gemini API key is read from environment configuration only.
- Provider errors are converted to the provider abstraction's error type; raw Gemini exceptions and API keys are never exposed through `POST /chat`.
- No database schema modifications or Alembic migrations required.

Dependencies:
- Added `google-genai>=0.5.0,<1.0` to `requirements.txt`.

Testing:
- Ran `pytest -q tests/test_gemini_provider.py tests/test_chat.py`: 27 passed.
- Ran `pytest -q`: 224 passed.
- Ran `git diff --check`: passed for project changes. Note: `app/schemas/obligation.py` has a pre-existing unrelated working-tree modification that is outside the scope of this phase and was not altered.

Commit:
- Phase 1h.2 completed in commit `3276d4d`.

Next Planned Step:
Phase 1h.4 — Financial Tool Calling

### Phase 1h.3 — Groq Fallback

Built:
- Added `GroqProvider` implementing the existing `LLMProvider` protocol in `app/core/chat/provider.py`.
- Added `FallbackLLMProvider` that tries Gemini first and automatically falls back to Groq only when the primary returns a `provider_error`.
- Guardrail rejections (`out_of_scope`, `injection`) and validation errors do NOT trigger fallback; they short-circuit before any provider is called.
- When both providers fail, `FallbackLLMProvider` returns a safe generic message: `"I'm having trouble connecting right now. Please try again later."`
- Reads `GROQ_API_KEY` from the environment via `app/core/config.py`; never hardcoded, logged, exposed, returned, or committed.
- Model name is configurable through `GROQ_MODEL` environment variable (default: `openai/gpt-oss-120b`).
- Converts domain `ChatMessage` representation into Groq request format inside `GroqProvider`.
- Converts Groq response into the existing domain `ChatResponse` shape.
- Passes tool definitions through the provider abstraction in OpenAI-compatible function-calling format (`type: "function"`, `function.name`, `function.parameters`, `required` array) verified against the selected model.
- Does NOT execute tools in this phase.
- `MockLLMProvider` retained for deterministic tests and as ultimate fallback when provider configuration is missing.
- No RAG yet.
- No conversation persistence or memory yet.
- Added 8 focused tests in `tests/test_groq_provider.py` covering initialization, missing API key, response mapping, tool definitions, OpenAI-compatible tool-definition conversion for `openai/gpt-oss-120b`, error handling, API key secrecy, no-content handling, and MockLLMProvider continuity.
- Added 5 fallback orchestration tests in `tests/test_chat.py` covering Gemini success without Groq invocation, Gemini failure invoking Groq, both providers failing producing a safe error, guardrail rejection not triggering fallback, and validation error not triggering fallback.

Security:
- Groq API key is read from environment configuration only.
- Provider errors are converted to the provider abstraction's error type; raw Groq exceptions and API keys are never exposed through `POST /chat`.
- No database schema modifications or Alembic migrations required.

Dependencies:
- Added `groq>=0.11.0,<1.0` to `requirements.txt`.

Testing:
- Ran `pytest -q tests/test_groq_provider.py tests/test_gemini_provider.py tests/test_chat.py`: 41 passed.
- Ran `pytest -q`: 238 passed.
- Ran `git diff --check`: passed for project changes. Note: `app/schemas/obligation.py` has a pre-existing unrelated working-tree modification that is outside the scope of this phase and was not altered.

Real API verification:
- Real Groq smoke test succeeded with model `openai/gpt-oss-120b`.
- Gemini real smoke test reached the API but returned temporary HTTP 503 model-capacity error; Gemini remains configured as primary and will be retried automatically.

Commit:
- Phase 1h.3 completed in commit `c6083ef`.

Next Planned Step:
Phase 1h.5 — Conversation Handling / Memory

### Phase 1h.4 — Financial Tool Calling

Built:
- Extended the chat domain with structured `ToolCall` support in `ChatResponse` so providers can return machine-readable tool requests alongside text.
- `GeminiProvider` extracts `function_call` parts from Gemini response candidates and maps them to domain `ToolCall` objects.
- `GroqProvider` extracts OpenAI-compatible `tool_calls` from Groq response messages and maps them to domain `ToolCall` objects.
- `FallbackLLMProvider` propagates `tool_calls` from the successful provider without provider-specific logic leaking into the route or service layers.
- Added a backend-controlled `ToolDispatcher` in `app/core/chat/tools.py` that validates arguments, routes only to known tools, enforces ownership via `UserContext`, and returns structured `ToolResult` objects.
- Implemented 7 backend-controlled financial tools:
  - `dashboard_summary` — read-only; reuses forecast logic for the authenticated user's current month.
  - `forecast` — read-only; delegates to `build_forecast()` with user-scoped obligations and financial profile.
  - `affordability` — read-only; delegates to `evaluate_affordability()` with user-scoped obligations and financial profile.
  - `list_obligations` — read-only; returns only obligations belonging to the authenticated user.
  - `create_obligation` — write; creates an obligation for the authenticated user only.
  - `update_obligation` — write; updates only an obligation owned by the authenticated user.
  - `delete_obligation` — write; deletes only an obligation owned by the authenticated user.
- Maintained strict separation between `ToolDefinition` (what the LLM sees) and backend `Tool` execution (what the backend runs). Tool definitions do not expose `user_id`; execution receives `UserContext` from the backend.
- `UserContext` remains the sole source of authenticated identity. The model cannot provide or override `user_id`, income, fixed expenses, or ownership.
- Ownership is enforced at the query boundary for read tools and at the execution boundary for write tools. Cross-user reads return empty results; cross-user writes return "not found".
- `forecast` and `affordability` tools delegate to the existing pure engines (`build_forecast()` and `evaluate_affordability()`). No financial calculation math is duplicated in the chatbot layer.
- Read tools (`dashboard_summary`, `forecast`, `affordability`, `list_obligations`) execute immediately without confirmation.
- Write tools (`create_obligation`, `update_obligation`, `delete_obligation`) require explicit backend-controlled confirmation before execution.
- Confirmation uses a module-level in-memory pending-confirmation store keyed by a SHA256 hash of `(user_id, tool_name, arguments)`. The key is single-use and user-scoped. Wrong user, wrong tool, wrong arguments, or reused/unknown keys are rejected before any execution.
- Implemented a tool-calling loop in `ChatService` with a hard limit of 5 iterations: send messages + tool definitions to the provider, execute requested tools, append results, and ask the provider for a final response.
- Structured tool results and safe error handling: unknown tools, invalid arguments, unauthorized access, missing resources, and database failures all return safe `ToolResult` objects without exposing raw exceptions, SQL errors, stack traces, or API keys.
- Tool execution is synchronous in this phase.
- No RAG yet.
- No conversation persistence or memory yet.
- Added 38 focused tests in `tests/test_tools.py` covering tool registry, security/ownership, read tools, write tools, confirmation flow, tool loop behavior, provider compatibility, and financial correctness.
- Note: confirmation state is in-memory and will be lost on process restart.

Security:
- The LLM can request a tool, but the backend authorizes and executes it. User identity, ownership, financial calculations, and database access remain backend-controlled.
- Write operations require explicit backend-verified confirmation; the LLM cannot generate its own authorization.
- No database schema modifications or Alembic migrations required.

Testing:
- Ran `pytest -q tests/test_tools.py`: 38 passed.
- Ran `pytest -q`: 276 passed.
- Ran `git diff --check`: passed for project changes. Note: `app/schemas/obligation.py` has a pre-existing unrelated working-tree modification that is outside the scope of this phase and was not altered.

Commit:
- Phase 1h.4 completed in commit `6e169ed`.

Next Planned Step:
Phase 1h.6 — RAG for Dabbarha Product Rules / Documentation

### Phase 1h.5 — Conversation Handling / Memory

Built:
- Added persistent `Conversation` and `ConversationMessage` SQLAlchemy models in `app/models/conversation.py`.
- Generated Alembic migration `17d4d0e39961_add_conversation_tables.py` creating `conversations` and `conversation_messages` tables with indexes and CASCADE deletes.
- Added `ConversationRepository` data-access layer in `app/core/chat/conversation.py` for conversation lifecycle and message persistence.
- Updated `ChatService` in `app/core/chat/service.py` to load bounded history (most recent 20 messages) and persist new messages to the conversation.
- Added `conversation_id` to the domain `ChatResponse` schema and to the API `ChatRequest`/`ChatResponse` schemas.
- `POST /chat` now accepts an optional `conversation_id`; when omitted, the backend creates a new conversation and returns the server-generated ID. When provided with an owned conversation, the request continues that conversation.
- Conversation ownership is enforced at the query boundary: `ConversationRepository.get_or_create_conversation()` validates `conversation_id + authenticated user_id` and raises `ValueError("Conversation not found")` for foreign or invalid IDs.
- History is bounded to the most recent 20 messages via `ConversationRepository.get_messages(limit=20)`; the current user message is appended after history loading and is never dropped.
- Stored message roles: `user`, `assistant`, and `tool`. Assistant tool calls store `tool_name` and `tool_arguments` (JSON). Tool results store `tool_name` and `tool_result` (JSON).
- Normalized tool-call history reconstruction in `_history_to_messages()` preserves `tool_name` and `arguments` for assistant tool-call messages, enabling correct provider-specific serialization.
- Updated `GeminiProvider._convert_messages()` to emit `function_call` parts for assistant tool-call history and to map `role="tool"` to `role="user"` for Gemini's API format.
- Updated `GroqProvider._convert_messages()` to emit OpenAI-compatible `tool_calls` for assistant tool-call history.
- Conversation memory is context only; it is never authoritative financial state. Financial truth continues to come from authenticated backend state/tools.
- Guardrails still apply to the current user message; historical content remains untrusted context and cannot bypass guardrails, authorize tools, override `UserContext`, override ownership, or alter financial truth.
- Confirmation authorization remains separate from conversation history: pending confirmations are stored in-memory, are single-use, and are keyed by `(user_id, tool_name, arguments)`. Conversation persistence does not store or reuse write authorization.
- No API keys, secrets, or raw provider SDK objects are persisted in conversation storage.
- No RAG in this phase.
- No unrelated features added.
- Added 14 focused tests in `tests/test_conversation.py` covering repository creation, ownership isolation, history bounds, message persistence, tool-call detail storage, conversation creation/continuation via `ChatService`, guardrail persistence, tool-call history persistence, provider compatibility, and confirmation flow with repository.
- Note: `app/schemas/obligation.py` has a pre-existing unrelated working-tree modification that is outside the scope of this phase and was not altered.

Security:
- Conversation ownership is strictly bound to the authenticated user ID; cross-user access returns a safe error.
- No database schema modifications beyond the new conversation tables and migration.
- Conversation history does not contain secrets, API keys, or raw provider objects.

Testing:
- Ran `pytest -q tests/test_conversation.py`: 17 passed, 1 skipped.
- Ran `pytest -q`: 293 passed, 1 skipped, 1 warning.
- Ran `git diff --check`: passed for project changes.

Commit:
- Phase 1h.5 completed in commit `3e2de0c`.

### Phase 1h.6 — RAG for Dabbarha Product Rules / Documentation

Built:
- Added a pure RAG module under `app/core/rag/` with zero FastAPI, HTTP, database, SQLAlchemy, authentication, or API dependencies.
- Implemented domain abstractions: `Document`, `DocumentChunk`, `RetrievalResult`, and `Retriever` protocol in `app/core/rag/schemas.py`.
- Implemented deterministic chunking in `app/core/rag/chunker.py` with configurable chunk size and overlap.
- Implemented a local deterministic TF-IDF embedding engine in `app/core/rag/embeddings.py` — no external embedding API or vector database required.
- Implemented an in-memory vector store with cosine similarity in `app/core/rag/store.py`.
- Implemented `KnowledgeRetriever` in `app/core/rag/retriever.py` with:
  - Path security: only reads from `docs/knowledge/`, rejects path traversal.
  - File filtering: only indexes approved `.md` and `.txt` files; excludes `.env`, `.db`, tests, source code, logs, and conversation history.
  - Top-k retrieval with configurable score threshold.
  - Lazy index building on first retrieval.
- Implemented document ingestion pipeline in `app/core/rag/ingestion.py`.
- Created 6 Dabbarha-owned knowledge documents in `docs/knowledge/`:
  - `index.md` — Knowledge base index
  - `affordability.md` — Affordability classification rules and thresholds
  - `forecast.md` — Forecasting documentation
  - `obligations.md` — Obligation properties, statuses, and ownership rules
  - `chatbot.md` — Chatbot capabilities and security model
  - `security.md` — Security model and data protection principles
- Added RAG configuration variables to `app/core/config.py`: `RAG_ENABLED`, `RAG_TOP_K`, `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_SCORE_THRESHOLD`.
- Integrated RAG into `ChatService` in `app/core/chat/service.py` with:
  - Lightweight deterministic documentation-vs-financial routing: `_is_documentation_question()` uses pattern matching to decide whether to consult RAG or rely on backend tools.
  - Documentation questions (e.g., "How does affordability classification work?", "What does Comfortable mean?") → RAG.
  - Personal financial questions (e.g., "What is my projected buffer?", "What are my obligations?", "Show my dashboard") → backend tools/database only; RAG is skipped.
  - Mixed questions (e.g., "How does Dabbarha define Comfortable, and am I Comfortable?") → both RAG and financial tools may be used.
  - Trust boundary: retrieved documentation is injected as `[DABBARHA DOCUMENTATION REFERENCE — UNTRUSTED DATA]` with explicit instructions that it cannot override system rules, authorize tools, override `UserContext`, override ownership, change financial calculations, request confirmation, or reveal secrets.
  - No-result behavior: when no relevant documentation exists for a documentation question, returns a safe "I don't have enough Dabbarha documentation..." response instead of fabricating rules.
  - Source attribution: structured `rag_sources` metadata (title, source path, chunk ID, relevance score) is preserved in `ChatResponse.metadata`.
  - RAG never executes or authorizes tools; `ToolDispatcher` remains authoritative for all financial operations.
- Cached `KnowledgeRetriever` at module level in `app/api/routes/chat.py` via `_get_knowledge_retriever()` to avoid rebuilding the entire index on every `POST /chat` request.
- Added 33 focused tests in `tests/test_rag.py` covering:
  - Domain abstractions (Document, DocumentChunk, RetrievalResult, Retriever protocol)
  - Deterministic chunking behavior
  - Local TF-IDF embedding engine
  - In-memory vector store search and scoring
  - KnowledgeRetriever: approved document loading, unapproved file exclusion, `.env`/`.db` exclusion, empty corpus, source metadata preservation, top-k respect, deterministic retrieval
  - Chat integration: documentation question uses RAG, personal financial question skips RAG, mixed question uses RAG, RAG context not persisted as financial truth, no-result safe response, source attribution in metadata, RAG prompt injection containment, guardrails still work with RAG
- Verified all existing chat, conversation, tool, Gemini, and Groq tests continue to pass without modification.

Security:
- RAG contains ONLY Dabbarha-owned product documentation in `docs/knowledge/`. No personal financial data, obligations, forecasts, affordability, or dashboard truth is indexed.
- `KnowledgeRetriever` only reads from the approved `docs/knowledge/` directory and rejects path traversal attempts.
- Only `.md` and `.txt` files are indexed; `.env`, `.db`, tests, source code, logs, and conversation history are never indexed.
- Retrieved documentation is treated as untrusted reference data, not executable instructions.
- Financial calculations, tool authorization, ownership enforcement, and `UserContext` remain backend-controlled.
- Conversation history is not entered into the RAG index.
- No external embedding API, vector database, or web search is used.

Testing:
- Ran `pytest -q tests/test_rag.py`: 33 passed.
- Ran `pytest -q`: 327 passed, 1 skipped, 2 warnings.
- Ran `git diff --check`: passed.

Commit:
- Phase 1h.6 completed in commit `f536cd2`.

### Phase 1h.7 — End-to-End Chat Orchestration & Hardening

Built:
- Verified the complete `POST /chat` flow: authenticated user → `GuardrailPolicy` → `ConversationRepository`/history → RAG when appropriate → Gemini → Groq fallback on `provider_error` → backend `ToolDispatcher` when the model requests tools → confirmation for write tools → final response → conversation persistence.
- Fixed provider initialization in `app/api/routes/chat.py`: `_get_chat_service()` now initializes `GeminiProvider` and `GroqProvider` in separate try/except blocks. Previously, a single broad `except Exception` caught failures from either provider and discarded a successfully mocked primary, causing tests and production fallback to incorrectly use `MockLLMProvider`.
- Fixed conversation ownership isolation in `app/core/chat/service.py`: when a user provides a `conversation_id` belonging to another user, the service now creates a new conversation for the authenticated user instead of returning an error with the foreign conversation ID.
- Fixed tool-result serialization in `app/core/chat/service.py`: tool results (which may be dicts, e.g., from `affordability`) are now serialized to JSON strings before being stored in `ChatMessage.content`, which expects `str`.
- Fixed `GeminiProvider._convert_messages()` in `app/core/chat/provider.py`: tool results are now sent as `Part.from_function_response` instead of `Part.from_text`, matching the Gemini function-calling API format.
- Fixed `GroqProvider._convert_messages()` in `app/core/chat/provider.py`: tool result messages now include `tool_call_id`, matching the OpenAI/Groq API format.
- Fixed e2e test patch paths in `tests/test_chat_e2e.py`: tests now patch `app.api.routes.chat.GeminiProvider` (and `GroqProvider`) instead of `app.core.chat.provider.GeminiProvider`, so mocks correctly intercept the route's provider instances.
- Updated `tests/test_conversation.py`: renamed `test_chat_service_rejects_foreign_conversation_id` to `test_chat_service_creates_new_conversation_for_foreign_id` to match the new ownership isolation behavior.
- Added 16 end-to-end integration tests in `tests/test_chat_e2e.py` covering:
  - Authenticated chat request
  - Unauthenticated request rejection
  - Empty/whitespace message rejection
  - Unrelated request out-of-scope response
  - Financial assistance request allowed
  - Injection request blocked
  - Normal financial question uses tools without RAG
  - Documentation question uses RAG
  - Mixed question uses both RAG and tools
  - Multi-turn conversation uses current state
  - Gemini success does not invoke Groq
  - Gemini failure invokes Groq
  - Guardrail rejection does not trigger fallback
  - Read tool execution and response
  - Write tool confirmation flow
  - Ownership isolation in tools
  - RAG injection resistance
  - Tool loop limit
  - No API key fallback to mock
  - Conversation ownership isolation
  - RAG sources in response metadata
  - No-result RAG safe response
- All 342 tests pass (1 skipped).

Security:
- Financial truth continues to come only from authenticated backend state/tools. RAG is explicitly marked as untrusted reference data and cannot authorize tools, override `UserContext`, override ownership, change financial calculations, request confirmation, or reveal secrets.
- Conversation ownership is strictly bound to the authenticated user ID; cross-user access creates a new conversation for the authenticated user.
- Write tools require explicit backend-verified confirmation; the LLM cannot generate its own authorization.
- `UserContext` remains the sole source of authenticated identity. The model cannot provide or override `user_id`.
- Conversation history is context only; it is never authoritative financial state and cannot authorize tool execution.

Testing:
- Ran `pytest -q`: 342 passed, 1 skipped, 1 warning.
- Ran `git diff --check`: passed for project changes.
- Ran `git status --short`: clean working tree with expected modifications.

Commit:
- Phase 1h.7 completed in commit `5cda880`.

### Phase 1i — Optional Financial Profile

Built:
- Registration now requires only name, email, and password. Monthly income, fixed expenses, and currency are no longer collected during registration.
- New users retain the existing defaults: `monthly_income = 0.00`, `fixed_expenses = 0.00`, `currency = EGP`.
- Added authenticated `PATCH /auth/me` for optional financial-profile updates.
- `PATCH /auth/me` supports partial updates for `monthly_income`, `fixed_expenses`, and `currency`.
- Identity/immutable fields (`id`, `email`, `name`, `password`, `password_hash`) cannot be changed through this endpoint.
- Creating obligations does not require financial information.
- Dashboard, Forecast, Affordability, and Chat behavior/calculation architecture were preserved.
- Updated affected tests to configure financial values through `PATCH /auth/me`.
- Added validation/security tests for the new endpoint.

Security:
- `PATCH /auth/me` is protected by `get_current_user` dependency.
- Only financial profile fields (`monthly_income`, `fixed_expenses`, `currency`) are updatable; identity fields are excluded.
- Partial updates are supported; omitted fields retain their current values.
- No database schema changes or Alembic migrations required.

Testing:
- Updated affected tests to configure financial values through `PATCH /auth/me`.
- Added validation/security tests for the new endpoint.
- Ran `pytest -q`: 365 passed, 1 skipped, 1 warning.
- Ran `git diff --check`: passed cleanly.

Commit:
- Phase 1i completed in commit `[pending]`.

Next Planned Step:
Phase 1j — Frontend Integration / Production Readiness

### Phase 2b.1 — JWT and Environment Configuration Hardening

Implemented and verified on `mohamed/backend`, starting from `2b13e37`.

- Removed the public development JWT signing-key fallback. All environments now require an explicitly configured key; there is no generated or legacy fallback key.
- Added validated development/test/production settings; unset APP_ENV safely means production. Configuration errors omit supplied values, and settings repr does not reveal credentials.
- Reject missing/empty/known-placeholder, undersized, low-diversity, repeated/sequential and template JWT keys; keep accepted secret bytes unchanged. These are weak-value checks, not proof of randomness.
- Preserved HS256, sub/exp token shape, the 60-minute default lifetime, JSON registration/login/token responses, existing Argon2id hashing, optional financial profiles and protected-route ownership/authentication.
- Verified actual environment loading: the application reads process variables only; explicitly selected Uvicorn `--env-file` files load before app import. Process variables win, and no automatic dotenv discovery occurs. No dependencies were added or updated.
- Defaulted docs/OpenAPI/ReDoc to disabled in production and enabled in development/test, with an explicit API_DOCS_ENABLED override. Kept debug false and existing public health behavior.
- Required CHAT_MOCK_ENABLED opt-in for local/test mock success; production rejects enabling it. Missing real-provider initialization now signals provider_error so real fallback is attempted. Disabled mocks/provider failure produce a safe HTTP 503; successful chat JSON remains unchanged. This is a configuration gate, not the broader Phase 2c protocol/confirmation repair.
- Ignored `.env.*` and `.envrc` while preserving `.env.example` and environment-specific `.example` templates. Added placeholder-only environment/configuration documentation.
- Isolated tests from local credentials and persistent databases using an ephemeral test-process signing key, empty provider keys, explicit mock opt-in and in-memory SQLite.
- Added regression coverage for missing/empty/default/placeholder/weak/valid secrets; safe startup errors; forged-token rejection and legitimate login; unchanged token lifetime/shape; docs/environment policy; actual Uvicorn file loading and precedence; and production-safe chat fallback.
- Corrected the pre-existing tamper test to alter significant signature bits rather than potentially equivalent base64url padding bits. This does not remediate the dependency advisory about noncanonical token text.
- Verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` — **454 passed, 2 warnings in 27.48s**. Existing Starlette/httpx and Google SDK/Pydantic warnings remain. `git diff --check` passed; branch/HEAD unchanged; no staged changes.
- No `.env` values, provider keys, existing signing secrets, packages, migrations, persistent user data, financial calculations or frontend files were changed. No paid-provider call, Git staging, commit, push or merge was performed.
- Deployment consequence: startup now fails for missing/rejected keys. Operators must supply an existing secure key or separately approve remediation; changing a deployed key invalidates its tokens. No automatic rotation or session invalidation was performed.
- Deferred: dependency advisories (including PyJWT parser issues), rate limiting, confirmation lifecycle, provider protocol/history, budget controls, validation/database fixes and admin scope. No production-readiness claim is made for this batch alone.

### Phase 2b.2 — Remove AI Chatbot from v1.0

Product decision: AI chat is outside v1.0, not a temporary outage. Inspected and preserved all existing uncommitted Phase 2b.1 security changes before removal; branch/HEAD remain `mohamed/backend` / `2b13e37`.

- Recorded an exact pre-deletion inventory: 32 chatbot-only source/test/RAG-document files, including the untracked Phase 2b.1 chat-policy test. Removed only these sources plus 47 compiled cache files belonging to retired modules/tests.
- Removed `/chat` registration/route, Gemini/Groq integrations, financial tool/confirmation layer, conversation repository/models/schemas, local RAG modules and the RAG-owned documentation corpus. `/chat` paths now return 404, with no fallback or feature flag that re-enables them.
- Removed `google-genai` and `groq` from runtime requirements; no unrelated requirement was upgraded/removed and no developer virtualenv uninstall was run.
- Removed AI/mock/provider/RAG settings, config exports, template variables, fixture flags and AI-only settings tests. The actual local environment files and provider credentials were not read, altered, printed or rotated.
- Preserved core financial engines/routes/schemas, user/obligation data, Argon2id/JWT code, HS256/sub/exp/60-minute defaults, explicit env-file handling, startup-secret validation, docs/debug policy and secret-file ignores. Verified 25 protected files byte-for-byte and all JWT/general settings validators unchanged from phase-start source snapshots.
- Removed only the User conversation relationship and conversation model exports. Retained `chatbot_entry` as historical obligation provenance and compatibility metadata; no financial row was relabeled or deleted.
- Preserved both applied Alembic revisions byte-for-byte. Added a narrow autogenerate filter for reflected, metadata-absent archival conversation tables so model removal does not propose drops. No new revision or destructive migration was created or run.
- Added six v1 release-boundary regressions: route/OpenAPI removal; startup with provider/retired-module import blockers; static dependency/import checks; financial CRUD/calculations and cross-user denial with synthetic legacy conversation rows; real Alembic autogenerate checking; and narrowly scoped filtering. Migration tests replay only existing upgrades on disposable in-memory SQLite.
- Full remaining suite: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` — **301 passed, 1 warning in 23.84s**. Focused release/settings/security/auth run: **149 passed, 1 warning in 14.68s**. Auth/settings/security account for 143 of the final passing cases. The existing Starlette/httpx warning remains; Google SDK warning no longer occurs.
- `git diff --check` passed; no staging, commit, push, branch change, merge, production/local DB operation or external provider call occurred. Both tracked and untracked files were reviewed.
- Added `docs/conversation-retirement.md` for separately approved retention/backup/forward-migration retirement and `docs/frontend-v1-handoff.md` with exact owner cleanup targets. Frontend worktree was inspected read-only and remains unchanged; its AI screen/shortcut/client cleanup is still required before public v1.0 release.
- Residual non-AI security work remains: dependency advisories, rate limiting, password/session policy, request/calendar/money validation, SQLite integrity, private caching/headers, operational readiness and archival-data retention. AI execution/injection/confirmation/cost risks are removed from this backend runtime rather than deferred as v1.0 features.

### Phase 2b.3 — Dependency Security Updates

Target confirmed by the owner: Ubuntu Server 24.04 LTS x86_64, current security-patched CPython 3.12, FastAPI/Uvicorn; PostgreSQL deployment/driver/schema work remains separate. Preserved existing local `.venv` and all uncommitted Phase 2b.1/2b.2 source changes.

- Built a clean isolated verification environment from the remaining backend requirements, with a separate pip-audit tool environment. No manual package purge or changes to the original `.venv` were performed.
- Updated only PyJWT 2.13.0 → 2.15.1, certifi 2026.7.22 → 2026.10.19 and Mako 1.4.1 → 1.4.3 among retained application/test distributions. Bootstrap pip in the new environment is 26.2.2. No major upgrade was selected; FastAPI, SQLAlchemy, Alembic, Uvicorn, Pydantic and Argon2 dependencies remain at the previously tested versions.
- The clean rebuild omits 11 obsolete distributions: charset-normalizer, cryptography, distro, google-auth, google-genai, groq, pyasn1, pyasn1-modules, requests, sniffio and urllib3. urllib3 is not a remaining backend dependency and was omitted rather than reintroduced merely to update it.
- Raised the direct PyJWT security floor; added exact 40-package Python 3.12 constraints and an Ubuntu x86_64 wheel hash lock. Root requirements resolve to exactly the tested versions. Linux marker/extras closure, wheel availability and published SHA-256 values were checked; the Linux lock replayed offline with binaries and mandatory hashes. Local macOS Argon2 binding built from source; the Linux target uses its abi3 wheel.
- New regression tests first reproduced uncaught RecursionError under old PyJWT. After the package update, nested/malformed tokens raise safe JWT errors and protected requests return 401. No app exception workaround, signature algorithm, claims, default expiration, password hash or API/financial calculation changes were introduced.
- Cross-version synthetic compatibility probe: a token and Argon2id hash generated under the original environment remain valid under the updated environment with the same synthetic credentials. No real key, token or password data was used.
- Before: OSV scanned 52 installed distributions and identified 19 distinct advisories across PyJWT/certifi/Mako/urllib3. Pip-audit 2.10.1 with OSV reported 38 alias records for those same issues. After: both scan paths checked 41 distributions including pip, with zero known advisories and no skipped packages in pip-audit. No claim is made about unpublished vulnerabilities or the untouched old environment.
- Final full suite in the clean environment: `PYTHONDONTWRITEBYTECODE=1 /Users/mohamedelgamily/Documents/Codex/2026-10-21/files-pasted-by-the-user-you/work/batch3/verify-venv/bin/python -m pytest -q -p no:cacheprovider` — **307 passed, 1 existing Starlette warning in 23.06s**. `pip check` reported no broken requirements. Existing in-memory migration/legacy-data and financial/ownership regressions pass.
- Verified local execution uses existing CPython 3.12.0 + SQLite. Linux compatibility checks are resolution/metadata/artifact checks, not execution on Ubuntu. No Docker/Podman runtime was available. Deployment must use a current security-patched interpreter and execute the suite on Linux before release; PostgreSQL integration was not attempted.
- Added `docs/dependencies.md` for clean installation, hash-lock scope, scan evidence and limitations. Update/use a newly built environment to receive fixes: the original `.venv` still holds its older vulnerable/retired packages by explicit instruction.
- No application/migration/financial source, frontend, real environment secret or persistent data changed. No dependency installation/scan invoked chatbot services. `git diff --check` and status review passed; no staging, commit, push, merge, rebase, reset, stash or branch change occurred.
- Dependency checks do not establish production readiness. Remaining non-dependency hardening, Linux execution, current Python patching at deployment, PostgreSQL integration and Jomana's frontend removal remain separate work.

## Historical Phase 1 Scope Note (superseded by later phases)

- Refresh tokens
- Full logout / token invalidation
- Additional dashboard endpoints beyond summary
- Extra API endpoints beyond completed auth, obligation CRUD, forecast, dashboard and affordability
- Additional infrastructure or abstractions

## Outstanding Launch Requirements

Before launch, configure and verify an externally reachable account-deletion request channel, apply and verify the encrypted-backup maximum retention of 30 days, rehearse safe PostgreSQL backup restoration with deletion WAL replay/quarantine, deploy and verify the required migrations, and complete legal/store and frontend reviews. These are deployment and product-operations requirements; Phase 2e does not claim they are active.

## Historical Design Decisions (superseded where Phase 2b.2 applies)

The backend starts as a modular FastAPI API. Forecasting logic now lives in `app/core/forecast.py` as a pure reusable module before any API or database integration.

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

Obligation update and delete endpoints use the authenticated user boundary for ownership checks and return generic 404 responses for both missing and cross-user records.

Forecasting is intentionally pure at Phase 1e.1: it accepts already-loaded obligation objects, performs month/date/status calculations in memory, and has no FastAPI, HTTP, database session, or SQLAlchemy query dependency.

Forecast API integration is a thin authenticated adapter over the pure forecast engine: the route validates forecast-window query parameters, loads the authenticated user's obligations, uses the authenticated user's stored income and fixed expenses, and delegates calculations to `app/core/forecast.py`.

Dashboard summary API is a thin authenticated adapter over the pure forecast engine: the route uses the authenticated user's stored income and fixed expenses, loads only the authenticated user's obligations, and delegates current-month calculations to `app/core/forecast.py`.

Affordability logic is pure domain logic at Phase 1g.1: it reuses the forecast engine, overlays proposed commitments on projected months, validates that the forecast window covers the entire commitment period, and returns a typed result without FastAPI, HTTP, database, or authentication dependencies.

The affordability API at Phase 1g.2 is a thin authenticated adapter over the pure affordability engine: the route enforces authentication, loads only the authenticated user's obligations and stored financial profile, derives the forecast window from the request, delegates evaluation to `app/core/affordability.py`, and maps the domain result to a typed response.

The chatbot at Phase 1h.1 is provider-agnostic and keeps financial truth in deterministic backend services: the route creates `UserContext` from the authenticated user, delegates to `ChatService` for guardrail decisions, and the `LLMProvider` abstraction is designed so Gemini or Groq can be plugged in later without changing the domain layer. Financial calculations remain the responsibility of `app/core/forecast.py` and `app/core/affordability.py`.

Gemini is integrated behind the existing `LLMProvider` abstraction at Phase 1h.2 using the current Google GenAI SDK. The provider reads its API key from environment configuration, converts domain messages to Gemini's request format, maps Gemini responses back to the domain shape, and passes tool definitions through for future function calling. No external provider logic leaks into the route or service layers.

Provider fallback is isolated behind the `LLMProvider` abstraction at Phase 1h.3: `FallbackLLMProvider` composes any two `LLMProvider` implementations and handles fallback logic entirely within the provider layer. The chat route and `ChatService` remain unaware of which provider is primary or fallback, and no provider-specific error handling or retry logic leaks into the domain or API layers.

The LLM can request a tool, but the backend authorizes and executes it. User identity, ownership, financial calculations, and database access remain backend-controlled. Write operations require explicit backend-verified confirmation. The model cannot generate its own authorization or override `user_id`.

Conversation memory provides context for the LLM but is never authoritative financial state. The backend remains the source of truth for authenticated identity, ownership, financial data, calculations, and tool authorization.

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
- Ran `pytest -q tests/test_forecast.py`: 14 passed.
- Ran `pytest -q tests/test_forecast.py tests/test_forecast_api.py`: 28 passed.
- Ran `pytest -q`: 156 passed.
- Verified `GET /health` continues to return `{"status": "ok"}`.
- Verified no new Alembic revisions were generated.
- Verified developer SQLite database `dabbarha.db` was not modified during testing.
- Verified `GET /obligations` returns only authenticated user's obligations and empty list when none exist.
- Verified `GET /obligations/{id}` returns 404 for nonexistent IDs and for obligations belonging to other users.
- Verified `PATCH /obligations/{id}` updates only authenticated user's obligations.
- Verified `DELETE /obligations/{id}` deletes only authenticated user's obligations.
- Verified `app/core/forecast.py` produces monthly forecasts without FastAPI or database integration.
- Verified `GET /forecast` is protected, uses only authenticated user financial values, loads only authenticated user's obligations, and delegates forecast calculations to `app/core/forecast.py`.
- Verified `GET /dashboard/summary` is protected, uses only authenticated user financial values, loads only authenticated user's obligations, and delegates current-month calculations to `app/core/forecast.py`.
- Verified `app/core/affordability.py` evaluates commitments across their full period, classifies using the worst projected month, and returns typed results without API or database dependencies.
- Verified `POST /affordability` is protected, uses only authenticated user financial values, loads only authenticated user's obligations, derives the forecast window from the request, and delegates evaluation to `app/core/affordability.py`.
- Verified `POST /chat` is protected, creates `UserContext` from the authenticated user, applies guardrail decisions, and delegates to the provider abstraction without external API calls.
- Verified `GeminiProvider` initializes from `GEMINI_API_KEY`, maps responses to the domain shape, forwards tool definitions, and never exposes the API key or raw provider exceptions.
- Verified `pytest -q`: 224 passed.
- Verified `git diff --check` passes for project changes. Note: `app/schemas/obligation.py` has a pre-existing unrelated working-tree modification outside the scope of this phase.
- Verified `POST /chat` supports structured tool calls, backend-controlled tool execution, and write-tool confirmation flow.
- Verified tool dispatcher routes only to known tools, enforces ownership via `UserContext`, and returns structured `ToolResult` without exposing raw database or provider exceptions.
- Verified `forecast` tool delegates to `build_forecast()` and `affordability` tool delegates to `evaluate_affordability()` with no duplicated financial math.
- Verified write tools require explicit backend-verified confirmation; wrong user, wrong tool, wrong arguments, reused keys, and unknown keys are all rejected.
- Verified `pytest -q`: 276 passed.
- Verified Phase 1h.5: persistent conversation storage with `Conversation` and `ConversationMessage` SQLAlchemy models, Alembic migration `17d4d0e39961_add_conversation_tables.py`, `ConversationRepository` data-access layer, authenticated user ownership enforcement, server-generated `conversation_id`, optional `conversation_id` on `POST /chat`, conversation continuation, bounded history of most recent 20 messages, user/assistant/tool message context, normalized tool-call history, Gemini/Groq-compatible tool-call history reconstruction, conversation memory is context only and never financial truth, financial truth continues to come from authenticated backend state/tools, guardrails still apply to current user messages, historical content remains untrusted context, confirmation authorization remains separate and in-memory, no API keys/secrets/raw provider SDK objects persisted, no RAG in this phase, no unrelated features, 14 focused conversation tests, full suite: 293 passed, 1 skipped, 1 warning.
- Verified `git diff --check` passes for project changes. Note: `app/schemas/obligation.py` has a pre-existing unrelated working-tree modification that is outside the scope of this phase and was not altered.
- Verified Phase 1h.7: end-to-end `POST /chat` flow with authenticated user, guardrails, conversation repository, RAG for documentation questions, Gemini primary with Groq fallback on `provider_error`, backend `ToolDispatcher` for tool requests, write-tool confirmation, final response, and conversation persistence.
- Verified Gemini → Groq fallback only triggers on `provider_error`; guardrail rejection, invalid input, and successful responses do not trigger fallback.
- Verified RAG is scoped to `docs/knowledge/` only; personal financial questions use backend tools/database without RAG; mixed questions use both RAG and tools.
- Verified financial truth comes only from authenticated backend state/tools; RAG context is injected with explicit untrusted-data boundary and cannot override system rules, authorize tools, override `UserContext`, override ownership, change financial calculations, request confirmation, or reveal secrets.
- Verified conversation ownership is enforced: foreign `conversation_id` values create a new conversation for the authenticated user.
- Verified tool-call history compatibility: Gemini emits `function_call`/`function_response` parts; Groq emits OpenAI-compatible `tool_calls`/`tool` messages with `tool_call_id`.
- Verified all 7 financial tools (`dashboard_summary`, `forecast`, `affordability`, `list_obligations`, `create_obligation`, `update_obligation`, `delete_obligation`) are backend-controlled and user-scoped.
- Verified write-tool confirmation: `create_obligation`, `update_obligation`, `delete_obligation` require explicit backend-verified confirmation; wrong key, wrong user, reused key, and unknown key are all rejected.
- Verified `pytest -q`: 342 passed, 1 skipped, 1 warning.
- Verified `git diff --check`: passed for project changes.
- Verified `git status --short`: clean working tree with expected modifications.
- Verified Phase 1i: registration requires only name, email, and password; monthly income, fixed expenses, and currency are no longer collected during registration.
- Verified new users retain defaults: `monthly_income = 0.00`, `fixed_expenses = 0.00`, `currency = EGP`.
- Verified `PATCH /auth/me` is protected, supports partial updates for `monthly_income`, `fixed_expenses`, and `currency`, and rejects identity/immutable field changes.
- Verified creating obligations does not require financial information.
- Verified Dashboard, Forecast, Affordability, and Chat behavior/calculation architecture were preserved.
- Verified affected tests configure financial values through `PATCH /auth/me`.
- Verified validation/security tests for the new endpoint.
- Verified `pytest -q`: 365 passed, 1 skipped, 1 warning.
- Verified `git diff --check`: passed cleanly.

## Phase 2b.4 — Input Validation & Database Integrity (verified)

- Preserved the uncommitted Phase 2b.1–3 work on `mohamed/backend`, HEAD `2b13e37c4ed6800f69915a97416d97b25bf0dd12`; no staging, commits, branch changes, frontend changes, real environment edits, persistent data writes or schema migrations.
- Centralized request money policy matching Numeric(12,2): finite 0–9,999,999,999.99 with at most two fractional digits; reject booleans, malformed, null, negative, excessive and overprecision input with 422.
- Applied the explicitly approved 1–1,200 month duration limit and calendar-overflow guards. Kept forecast's 1–60 month range and existing monthly calculation semantics. No down-payment fields or price/payment relationship rules.
- Trimmed required Unicode text before existing length checks; rejected explicit null updates and validated final merged obligation state before mutation. Optional financial-profile defaults and valid API contracts remain intact.
- Enabled SQLite foreign keys on every new application connection. Added explicit profile/request rollback paths and safe SQLAlchemy error responses; validation errors no longer echo raw inputs (including non-finite JSON numbers).
- Added 126 regression cases, including rollback/recovery after real failed flushes and operational errors, cross-user ownership, extreme dates/integers, legacy duration read compatibility, optional profile and monetary boundaries.
- Full clean Phase 2b.3 environment suite: **433 passed, 1 existing Starlette/httpx warning in 28.68s**. `pip check`: no broken requirements. `git diff --check`: passed. Original `.venv`, migrations, dependency files and financial engine sources preserved.
- Read-only frontend contract review completed; valid requests remain compatible. New amount/duration restrictions may return 422 for inputs currently accepted by client forms. Legacy invalid records are not rewritten; updates must satisfy merged-state policy.
- PostgreSQL execution, legacy-data remediation, direct-SQL precision enforcement and broader audit items remain deferred. See `docs/validation-integrity.md` for exact limits and remaining risks. Dependency scan was not rerun because this phase made no dependency changes.

## Phase 2b.5 — Rate Limiting & API Security (verified)

- User approved the Redis architecture and configurable defaults. Preserved Phases 2b.1–2b.4 on `mohamed/backend`, HEAD `2b13e37c4ed6800f69915a97416d97b25bf0dd12`; no staging, commits, pushes, frontend, real secrets, persistent records, migrations or financial formulas changed.
- Added atomic Redis sliding-window quotas shared by workers: failed/in-flight login 5/account+IP/15 minutes, total login 30/IP/15 minutes, registration 5/IP/hour, writes 60/user/minute, reads 120/user/minute, plus forecast 30/user/minute and affordability 10/user/minute. Keys contain HMAC digests, never raw identifiers. Safe 429 includes Retry-After.
- Production requires private Redis and a separate explicit HMAC key; memory mode is rejected. Missing configuration/connectivity blocks startup; runtime backend failures return safe 503 instead of bypassing limits. Memory storage is bounded and restricted to development/test.
- Added equivalent dummy Argon2 verification for unknown accounts, per-worker concurrency 2 with a 0.25-second bounded wait, finite login reservations and safe overload handling. Existing registration 409 enumeration risk is explicitly retained, as approved; no account flow, stored hash or token/session changes.
- Added 64-KiB actual/declaration body limits, 64-level JSON guard, 10-second body-read deadline, safe errors/log redaction and no-store/nosniff/no-referrer response headers. CORS remains closed. Forwarded identity comes only through the explicitly trusted Uvicorn/proxy connection context.
- Added inactive private Redis/Caddy and production environment templates; no deployment was activated. HSTS belongs to the verified HTTPS proxy boundary. See `docs/api-security.md` for all settings, counting rules and remaining risks.
- Added redis 8.1.0 only; all existing dependency versions preserved. Rebuilt a new clean environment, verified 41 Linux CPython 3.12 wheel hashes/marker closure and offline lock replay; pip check clean. OSV pip-audit: 42 distributions, zero known advisories, zero skips.
- Verification: **485 passed, 1 warning in 32.01s**, no skips, in the new clean Phase 2b.5 environment. Includes all 433 previous tests plus 52 new cases. Actual disposable Redis 7.4.11 (official archive checksum verified, TCP disabled) tests concurrency, expiry, startup/outages and three independent processes sharing a quota. `git diff --check` passed; staged diff empty and frontend clean.
- Local CPython 3.12.0/macOS + SQLite only. Linux wheels were verified; actual Ubuntu/PostgreSQL/Caddy deployment, load sizing, edge DDoS protection, Redis history durability/failover and broader audit items remain separate work. No production-readiness claim.

## Phase 2b.6 — Authentication & Session Security (verified locally; production deployment pending)

- Started from clean `mohamed/backend` at `e4e452c35df27f7214b45fd394621be7b2d5c70f`. Preserved Phases 2b.1–5, existing Argon2id hashes, JWT key/HS256, legacy login's two response keys and configured 60-minute default. No frontend edits, real secret changes or persistent migrations/data writes.
- Implemented the approved 8–128 Unicode-code-point registration policy without trimming/normalization/composition rules; legacy login lengths remain accepted. Generic login errors, dummy verification and registration duplicate-email 409 remain. Added safe malformed numeric JWT claim rejection.
- Added opt-in durable sessions with unique sid/jti access JWTs (15 minutes), opaque hashed 256-bit refresh credentials, 30-day refresh inactivity and 90-day absolute lifetime. Protected requests check database session state; revocation survives workers/restarts when deployed with the shared database. Feature defaults disabled pending migration/key/worker/mobile rollout.
- Added reviewed additive revision `6b6a00000001` creating auth_sessions, auth_refresh_tokens and legacy_access_revocations, with UTC epoch BIGINT times for SQLite/PostgreSQL portability. Fixed Alembic's ConfigParser handling of percent-encoded database URLs in `alembic/env.py`; SQLAlchemy receives the original URL. The migration upgrade/downgrade integration test passed on fixture-created disposable SQLite and PostgreSQL databases. No persistent migration was executed.
- Added POST /auth/sessions, POST /auth/refresh, GET /auth/sessions, POST /auth/sessions/{sid}/revoke (password confirmation) and POST /auth/logout. Preserved existing login/registration/financial contracts. Legacy logout uses a verified fingerprint; one device session equals one entire refresh family, other device families remain valid.
- Implemented atomic bounded encrypted response receipts: same old token plus same random 256-bit retry key can recover the exact pair for 60 seconds, maximum two recovery responses, without extending expiration. Different-key conflicts inside the window return 409; different-key reuse afterward commits that family revocation before 401. Recognized late/exhausted duplicates return 409 without new credentials. Revocation and successor consumption erase recoverable receipt data.
- Receipt encryption uses AES-256-GCM with a separate explicit 32-byte base64 key, random 96-bit nonce, authentication tag and bound associated data. No plaintext tokens in database records/logs. SQLite BEGIN IMMEDIATE and PostgreSQL row-lock transaction paths share the protocol; independent-process atomic recovery tests passed on SQLite. Cleanup preserves consumed hashes until family absolute expiry, clears expired ciphertext and removes expired families in bounded batches.
- Added explicit refresh IP/session quotas and shared existing login/Argon2/user quotas, safe 429/503 behavior, fail-closed storage/encryption paths and SQL parameter suppression. Financial calculation source files were not edited. Optional profile and financial response equality/ownership are tested with new session JWTs.
- Clean isolated environment adds only pycryptodomex 3.24.1, psycopg 3.3.6 and psycopg-binary 3.3.6; every previous distribution version is unchanged. Rejected cryptography 48.0.1 after three distinct advisories (six duplicate scan records); final rebuilt environment omits it. pip check passed; final advisory scan: 45 distributions including pip, zero advisory hits/skips. All 44 target Linux wheel hashes, marker/extra closure, offline hash-lock replay and root constraints resolution passed; actual Ubuntu execution is not claimed.
- Final external verification on macOS using the clean isolated environment and fixture-created disposable services: **2 migration tests passed, 1 existing warning in 3.61s; full backend suite 591 passed, 1 existing Starlette/httpx warning in 85.81s**. The runner set `REQUIRE_REDIS_TESTS=1` and `REQUIRE_POSTGRES_TESTS=1`; both integration services were required, and the full-run summary reports no skips or deselections. Logs: `outputs/Phase-2b6-External-Migration-Tests.txt` and `outputs/Phase-2b6-External-Full-Tests.txt` in the task outputs folder. Earlier sandbox-only attempts could not start PostgreSQL shared memory or the Redis Unix socket; those constrained runs are superseded by this successful external verification.
- git diff --check passed and staged diff is empty. Frontend remains clean at 1c144d4f8f3a384589c24474381500876dc09405. Documentation and blank-key examples describe rollout, key provisioning, precise replay behavior and Jomana's SecureStore/single-flight/cache/logout handoff; no frontend work was implemented.
- Verification establishes local macOS integration behavior with disposable SQLite, PostgreSQL and Redis; it does not establish production deployment readiness or actual Ubuntu execution. Remaining rollout gates include target Linux execution, operational review and execution of the additive migration on a backed-up deployment database, separate receipt-key provisioning, frontend/native SecureStore and single-flight integration, and legacy-token retirement. Bounded replay recovery permits replay of a complete captured request inside its limit; long outages/storage failures can require sign-in. No production migration or credential change was performed.

## Future Updates

Use this section to record progress in later phases.

- Future consideration: the current database uses `0.00` defaults for `monthly_income` and `fixed_expenses`, so the backend cannot distinguish between "financial profile not configured" and "user explicitly entered zero income." A future schema change (e.g., nullable fields or a separate profile-configuration flag) may be needed to support this distinction.

## Phase 2c.1 — Optional Down Payments & Installment Calculations (verified with disposable local integrations; production deployment not verified)

- Added opt-in installment plan creation and explicit legacy conversion. `purchase_price` is authoritative for calculations; `total_amount` remains a compatibility snapshot for new plans. Legacy rows with no plan marker retain their previous recurring monthly calculation and are never silently recalculated. Conversion requires reviewed plan values and affirmative confirmation; existing status is preserved unless explicitly changed.
- Added manual provider monthly installments, automatic no-interest, flat nominal annual interest and reducing-balance nominal annual interest. Rates accept 0–100% with up to four decimal places; no APR or unentered fees are calculated. Manual payment amounts remain exactly as entered, including when disclosed rate metadata is stored.
- Added integer-cent/Decimal schedule generation, `ROUND_HALF_UP`, persisted payment rows, principal/interest reconciliation, flat final-row cent remainder, reducing-balance final-payment payoff adjustment, calendar-clamped due dates, and Numeric(12,2)/aggregate limit checks. Plan edits atomically replace rows using `schedule_version` compare-and-swap; stale edits return 409. Failed writes roll back. The table supports future variable rows; v1.0 manual plans repeat one provider amount.
- Added exact-date down payments. Paid amounts are excluded from projection; unpaid due amounts appear once with original date and overdue status in the forecast's first month. Forecast/dashboard retain legacy aggregate keys and add schedule/down-payment breakdowns. Plan-aware affordability evaluates the generated payment schedule; the existing monthly-amount affordability contract and all legacy financial formulas remain in place.
- Added additive migration `2c1a00000001_installment_plans.py`, owned schedule retrieval, rate/amount/term/date validation, cross-user schedule isolation, response compatibility coverage, conversion confirmation, optimistic concurrency, arithmetic boundary cases, and SQLite migration upgrade/downgrade/re-upgrade coverage. No persistent database migration, frontend edit, dependency change, or secret change was made.
- Added Jomana's English/Egyptian Arabic UI handoff and technical policy in `docs/installment-plans.md`; the fail-fast `scripts/run-phase-2c1-verification.sh` requires actual disposable Redis/PostgreSQL binaries and checks existing dependency pins without installing or upgrading packages.
- External macOS verification log `Phase-2c1-External-Verification.log` records CPython 3.12.0, Redis 7.4.11, PostgreSQL 18.6, all 44 exact dependency pins, `pip check` success, and no known `pip-audit` findings. SQLite and PostgreSQL migration upgrade/downgrade/re-upgrade tests passed (**2 passed**); the full suite collected 613 tests and finished **613 passed, 0 failed, 0 skipped, 1 existing Starlette/httpx warning in 56.45s**. Both Redis and PostgreSQL tests were mandatory and ran against disposable local services. No persistent database was migrated.
- Post-log review added a dashboard regression for persisted schedule totals and an overdue down payment; that targeted test passed on the isolated SQLite test database. A subsequent full rerun in the Codex sandbox could not initialize PostgreSQL because the sandbox denied System V shared memory (`shmget: Operation not permitted`). This is a sandbox limitation, not a PostgreSQL migration failure: the saved external log records both PostgreSQL migration tests and the complete 613-test run passing. The final recorded evidence is therefore the 613-test external suite plus the added targeted dashboard test; a 614-test full-suite rerun was not available in this sandbox.
- `git diff --check` passes. The local integration run does not verify Ubuntu production deployment, production PostgreSQL provisioning, or frontend/native implementation; no production-readiness claim is made.

## Phase 2d — Payment Reminders & Push Notifications (verified with disposable local integrations; production/device rollout not verified)

- Added additive migration `2d1a00000001_payment_reminders.py` with six owned tables for preferences, session-bound push devices, payment occurrences and their audit events, notifications, and per-device deliveries. The migration was tested through upgrade/downgrade/re-upgrade paths on disposable SQLite and PostgreSQL databases; no persistent database was migrated.
- Added idempotent, ownership-scoped occurrence materialization for exact installment rows and clamped legacy monthly due dates. Mark as Paid and Undo record audit events; paid down payments are not projected as unpaid, mark-paid cancels pending reminders, and undo does not replay expired reminder offsets. Schedule edits supersede pending occurrences while retaining confirmed history.
- Added bilingual English/Egyptian Arabic notification copy with private-by-default lock-screen content, preference/time-zone/quiet-hour handling, session-bound encrypted Expo token storage, notification history/read APIs, and a separately supervised worker with atomic delivery claims, retries, receipt checks and stale-session suppression. API startup does not launch the worker or contact Expo; notification and delivery settings remain disabled by default.
- Added API/configuration documentation, the mobile handoff for Jomana, a systemd deployment template, blank-key environment examples, and the external verification runner. No frontend source, production credentials, financial formulas, or persistent user data were modified.
- Independently reviewed the saved external run at `/var/folders/qr/4cyr66v509jcksbt3gxr_10w0000gn/T/dabbarha-phase-2d-verification-20261021-234137.log`: all 44 exact dependency pins matched; `pip check` passed; `pip-audit 2.10.1` reported no known vulnerabilities; disposable SQLite/PostgreSQL migration and concurrent-worker tests ran **4 passed**; the complete suite ran **628 passed, 0 failed, 0 skipped, 1 existing Starlette/httpx deprecation warning** in 66.03 seconds. Redis and PostgreSQL integration tests were mandatory and passed. The runner exited 0 and `git diff --check` passed.
- Verification establishes behavior on macOS with disposable local SQLite, PostgreSQL 18.6 and Redis 7.4.11 only. It does not verify production deployment, production database migration, Expo/APNs/FCM delivery, or real iOS/Android devices. The frontend handoff and production rollout remain separate work; this is not a production-readiness claim.

## Phase 2e — Account Deletion & Privacy (verified with disposable local integrations; deployment and store requirements pending)

- Added authenticated `DELETE /auth/account`. The caller must present the existing access token, re-enter the current password (verified with the existing Argon2id hash), and explicitly confirm permanent deletion. It deletes the authenticated account only, returns 204 after the transaction commits, and fails safely on password, storage, or lock errors. Existing authentication and financial response contracts remain unchanged.
- Added an additive migration, `2e1a00000001_account_deletion_identity.py`, for a single PII-free SQLite account-ID high-water mark. This prevents SQLite from reusing a deleted maximum user ID while a legacy access JWT could still be valid; it stores no deleted-user list. PostgreSQL continues using its native identity sequence. Upgrade, downgrade, and re-upgrade were exercised only on disposable databases.
- Account deletion cascades the user profile and financial profile, obligations and installment schedules, payment occurrences and audit events, notification preferences/history/deliveries, encrypted push-device tokens, sessions/refresh-token rows and legacy revocations, plus legacy conversation/message data. Tests verify that legacy and session access tokens and refresh credentials fail after deletion, rollback leaves all related data intact, and cross-user records remain isolated.
- Coordinated the notification sender and deletion endpoint with the same bounded per-user database lock. The worker rechecks eligibility and device/session state while holding that lock through the provider request (whose production HTTP timeout is five seconds); lock waits are bounded. A provider-accepted notification may still arrive after deletion completes, but no new send begins after the deletion response.
- Added the public bilingual informational route `/privacy/account-deletion`, English/Egyptian Arabic deletion disclosures, `docs/account-deletion.md`, and `docs/frontend-account-deletion-handoff.md`. The public page currently explains the process but does not receive or process external deletion requests; the publisher must configure a real support/request channel before publishing it as the store's external deletion path. No support address or service is claimed to exist.
- Independently inspected external verification log `/var/folders/qr/4cyr66v509jcksbt3gxr_10w0000gn/T/dabbarha-phase-2e-verification-20261022-001359.log`. It records **18 focused SQLite/PostgreSQL migration, cascade, rollback, token, and worker-race cases passed** (one existing warning), then **648 passed, 0 failed, 0 skipped** in the complete suite (one existing Starlette/httpx deprecation warning; 73.25 seconds). Redis and PostgreSQL integrations were mandatory. All 44 exact dependency pins matched; `pip check` passed; `pip-audit 2.10.1` reported no known vulnerabilities; the runner exited 0 and final Git/diff checks passed.
- Additional review found no frontend changes, persistent database files, production secrets, or credential-shaped tokens among the changed files. No production migration or deployment operation was performed. `git diff --check` and shell syntax checks passed.
- Deployment requirements remain unverified: an external deletion-request channel must be made operational; encrypted backups must be configured to expire within the approved 30-day maximum; and restoration must use an isolated restore with complete post-backup WAL/deletion replay and orphan checks rather than activating an old snapshot directly. A snapshot-only restore can resurrect a deleted account; this phase adds no deletion ledger. The public information page alone does not establish Google Play compliance. No production-readiness, production-deployment, backup-control, or store-compliance claim is made.

## Phase 2f.1 — Secure Admin Identity & TOTP Authentication (locally verified; production deployment pending)

- Added default-off administrator roles (`user`, `admin`, `superadmin`) with an additive migration that defaults existing accounts to ordinary users, plus a privacy-conscious audit table whose actor/target references are cleared if an account is deleted. There is no public role elevation endpoint.
- Added interactive offline provisioning and revocation for existing accounts. Provisioning enrolls a six-digit TOTP factor and stores it only as AES-256-GCM authenticated ciphertext under a dedicated 32-byte key; revocation removes the factor and revokes the account's durable sessions and refresh-recovery receipts. Web requests cannot provision or change roles.
- Added `POST /admin/auth/step-up` and `GET /admin/auth/me`. Admin authentication requires an existing v2 device session and a fresh TOTP code. A step-up token is bound to that session, expires after five minutes by default (configurable from 1–15 minutes), and is invalidated by session revocation or a current-role change. TOTP steps are single-use under concurrent requests. Admin endpoints return 404 while disabled; enabling them requires durable sessions, disabled legacy token issuance, and the dedicated encryption key. Legacy JWTs cannot step up to admin access.
- Phase 2f.1 grants no financial-data access, standing support permission, account impersonation, or financial mutation capability. Phase 2f.2 operational APIs are documented below. The approved future model remains staged for Phase 2f.3: specific-user, fixed-scope, read-only temporary support grants with case/reason, recent MFA, a 15-minute maximum, detailed audit, independent approval preferred, and exceptional self-approval distinctly recorded and alerted. The browser dashboard is also pending.
- Added migration/admin security tests, deployment configuration guidance, and a future browser-client handoff. No frontend files, real credentials, persistent databases, or user records were changed; the migration was exercised only against disposable SQLite and PostgreSQL databases.
- Independently inspected `/var/folders/qr/4cyr66v509jcksbt3gxr_10w0000gn/T/dabbarha-phase-2f1-verification-20261022-010200.log`: CPython 3.12.0 on macOS x86_64; all 44 exact dependency pins matched; `pip check` passed; `pip-audit 2.10.1` found no known vulnerabilities; targeted SQLite/PostgreSQL admin and migration tests passed (**18 passed**, one existing Starlette/httpx deprecation warning); full suite **665 passed, 0 failed, 0 skipped**. The run required and passed Redis 7.4.11 and PostgreSQL 18.6 integrations, and ended with verification exit status 0 and clean diff checks.
- This verifies Phase 2f.1 on the local macOS test setup with disposable services only. It does not establish production deployment, production migration, production key provisioning/rotation, audit retention/alerting, or browser-dashboard readiness. The agreed 12-month audit retention and alerting remain deployment and privacy/legal review requirements; TOTP recovery and key-rotation operations require a reviewed operator procedure. Phase 2f.3 and the browser dashboard remain explicitly pending.

## Phase 2f.2 — Admin Operational APIs & User Management (implemented and locally verified; production deployment pending)

- Added default-off, read-only operational APIs for aggregate overview metrics, system/database/Redis/worker health, exact account lookup, bounded session/device metadata, and paginated notification-delivery diagnostics. Every operational request requires a current durable v2 session, an `admin` or `superadmin` role, and an unexpired, session-bound TOTP step-up token. Ordinary users, legacy access tokens, and disabled deployments cannot access the operational APIs.
- Account lookup requires exactly one exact account ID or normalized email; it does not provide wildcard or directory search. Operational responses omit financial profiles, obligation amounts, payment data, credentials, token material, raw push tokens, notification bodies, and raw provider errors. Admin and admin-IP Redis quotas are configurable and fail closed; administrative access and denied attempts are audited with bounded action/outcome values and an HMAC source fingerprint.
- Added account-free notification-worker heartbeat telemetry and health status. Heartbeat timestamps are UTC-aware in application code, PostgreSQL uses `TIMESTAMP WITH TIME ZONE`, and SQLite's naive stored values are interpreted as UTC. Status calculations and API output normalize PostgreSQL connection-local timestamps to UTC. The Africa/Cairo regression verifies correct instant conversion, age/staleness, last-success preservation, current failed-cycle time and UTC serialization.
- Added the additive `2f2a00000001_admin_worker_heartbeat.py` migration and disposable SQLite/PostgreSQL upgrade/downgrade/re-upgrade tests. PostgreSQL fixture failures now display sanitized `initdb` diagnostics. Operational API documentation and the browser-dashboard handoff are included; no dashboard UI or frontend changes were made.
- Independently inspected `/var/folders/qr/4cyr66v509jcksbt3gxr_10w0000gn/T/dabbarha-phase-2f2-verification-20261022-152738.log`: **46 focused admin/migration tests passed**; the complete backend suite reported **694 passed, 0 failed, 0 skipped** with one existing Starlette/httpx deprecation warning. SQLite and PostgreSQL migration cases, PostgreSQL timezone regression, required disposable PostgreSQL and real Redis integrations all passed. CPython 3.12.0 on macOS x86_64 matched all 44 dependency pins; `pip check` passed; `pip-audit 2.10.1` found no known vulnerabilities; the runner exited 0 and its diff and changed-file secret checks passed.
- Verification used disposable local SQLite, PostgreSQL 18.6 and Redis 7.4.11 services only. It does not establish production deployment or production migration. Pending requirements include shared private production Redis, durable-session and TOTP-key provisioning, production role provisioning, external API/database/Redis/worker monitoring, and the approved audit retention/alerting policy after privacy/legal review. Phase 2f.3 temporary financial-support access and the browser admin dashboard remain pending; no production-readiness claim is made.

## Phase 2f.3 — Controlled Financial Support Access (implemented and locally verified; production deployment pending)

- Added temporary, target-specific support grants for fixed financial-data scopes. Grant requests require an existing target, bounded non-identifying case reference, structured reason, and one or more allowlisted scopes. Grants expire 15 minutes after request; approval does not extend the lifetime. Only current superadmins with a live v2 device session and recent MFA may request, approve, inspect, or revoke grants. Explicit self-approval is supported for the initial single-admin case and produces a separate enhanced audit event.
- Added scoped, read-only, paginated endpoints for financial profiles, obligations, persisted installment schedules, and payment statuses. Every sensitive read is bound to the target, grant scope, original requesting session, current role, active target account, and an individually verified, atomically consumed TOTP step. Responses use established schemas, have `Cache-Control: no-store`, and do not provide impersonation, edits, payment actions, wildcard search, or bulk export.
- Added the additive migration `2f3a00000001_financial_support_grants.py`; target deletion cascades grants and clears target/grant references in audit rows. Audit events record approvals, exceptional self-approval, inspections, reads, denials, revocations, and observed expirations without case text, MFA codes, tokens, or financial values. Database failures fail closed. No persistent database migration or production data operation was performed.
- Added focused tests for SQLite and PostgreSQL covering grant scopes and expiry, self/independent approval, per-read TOTP replay protection and concurrency, revoke/read races, role changes, account deletion, response privacy, operational-admin denial, and safe database-failure behavior. Added `docs/admin-financial-support.md`, updated admin/dashboard handoff documentation, and added `scripts/run-phase-2f3-verification.sh` for repeatable external verification against disposable services.
- Independently reviewed external log `/var/folders/qr/4cyr66v509jcksbt3gxr_10w0000gn/T/dabbarha-phase-2f3-verification-20261022-161411.log`: focused SQLite/PostgreSQL support tests **18 passed**; migration and release checks **3 passed**; full suite **712 passed, 0 failed, 0 skipped** (one existing Starlette/httpx deprecation warning). Disposable PostgreSQL 18.6 and Redis 7.4.11 integrations, including concurrent TOTP replay and revoke/read checks, passed. All 44 exact dependency pins matched, `pip check` passed, `pip-audit` found no known vulnerabilities, and the runner exited 0.
- Verification establishes behavior on the local macOS test setup with disposable SQLite, PostgreSQL, and Redis services only. It does not establish production deployment, production migration, production monitoring, audit-retention enforcement, or operational alerting. Phase 2g, the browser admin dashboard, production deployment, monitoring, the approved 12-month audit-retention policy, and operational alerts remain explicitly pending. No production-readiness claim is made.
