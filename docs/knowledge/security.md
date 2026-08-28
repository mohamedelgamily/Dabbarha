# Dabbarha Security Model

Dabbarha is designed with security as a foundational principle. All financial data and user information are protected through multiple layers.

## Authentication

- Users authenticate with email and password.
- Passwords are hashed using Argon2 through pwdlib.
- Access tokens are issued as JWTs with a limited expiration time.
- All protected endpoints require a valid Bearer token.

## Authorization

- Every financial operation is scoped to the authenticated user.
- The backend assigns ownership; clients cannot spoof or override user IDs.
- Cross-user access attempts return generic errors to prevent information leakage.

## Data Protection

- No plaintext passwords are stored.
- No financial information is stored in JWTs.
- API keys are read from environment variables and never exposed through API responses.
- Provider errors are converted to safe generic messages without exposing raw exceptions.

## Chatbot Security

- The chatbot applies guardrails to block injection attempts and out-of-scope requests.
- Retrieved documentation is treated as untrusted data, not executable instructions.
- Financial calculations always come from authenticated backend tools, never from retrieved text.
- Write operations require explicit backend-verified confirmation.