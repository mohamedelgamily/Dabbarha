"""Isolate tests from local credentials and persistent databases."""
import os
import secrets

# Applied before application modules are imported; values live only in this process.
os.environ.update(
    APP_ENV="test",
    RATE_LIMIT_BACKEND="memory",
    SESSION_AUTH_ENABLED="false",
    SESSION_LEGACY_ISSUANCE="true",
    SESSION_LEGACY_ACCEPTANCE="true",
    JWT_SECRET_KEY=secrets.token_urlsafe(48),
    JWT_ALGORITHM="HS256",
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES="60",
    API_DOCS_ENABLED="true",
    DATABASE_URL="sqlite:///:memory:",
)


import pytest


@pytest.fixture(autouse=True)
def isolated_request_protection(monkeypatch):
    from app.main import app
    from app.core.api_security import SecurityRuntime
    from app.core.api_security_settings import APISecuritySettings
    monkeypatch.setattr(app.state, "security", SecurityRuntime(APISecuritySettings()))
