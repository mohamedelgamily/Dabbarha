"""Configuration regressions use synthetic credentials, never local .env values."""
import os
from pathlib import Path
import secrets
import subprocess
import sys

import pytest

from app.core.settings import ConfigurationError, Settings

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OLD_DEFAULT = "development-only-insecure-jwt-secret-change-me"


def environment(**overrides: str) -> dict[str, str]:
    return {"JWT_SECRET_KEY": secrets.token_urlsafe(48), **overrides}


@pytest.mark.parametrize("mode", ["development", "test", "production"])
@pytest.mark.parametrize("value", [None, "", "   ", PUBLIC_OLD_DEFAULT, "changeme", "change-me-before-production-0123456789", "your-jwt-secret-key-at-least-32-characters", "replace-with-a-secure-random-secret", "placeholder" * 8, "a" * 64, "abc123" * 16, "short-secret", "<YOUR_EXISTING_OR_SECURELY_GENERATED_SECRET>", "{{GENERATE_A_SECURE_RANDOM_SECRET_HERE}}", "0123456789abcdefghijklmnopqrstuvwxyz"])
def test_rejects_missing_placeholder_or_weak_secret(mode: str, value: str | None) -> None:
    env = {"APP_ENV": mode}
    if value is not None:
        env["JWT_SECRET_KEY"] = value
    with pytest.raises(ConfigurationError) as exc:
        Settings.from_environ(env)
    assert "JWT_SECRET_KEY" in str(exc.value)
    if value and value.strip():
        assert value not in str(exc.value)


@pytest.mark.parametrize("mode", ["development", "test", "production"])
def test_valid_secret_preserved_exactly_and_not_represented(mode: str) -> None:
    env = environment(APP_ENV=mode)
    settings = Settings.from_environ(env)
    assert settings.jwt_secret_key == env["JWT_SECRET_KEY"]
    assert settings.jwt_secret_key not in repr(settings)
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 60


def test_default_environment_is_production_with_no_docs() -> None:
    settings = Settings.from_environ(environment())
    assert settings.app_env == "production"
    assert settings.api_docs_enabled is False


@pytest.mark.parametrize("mode", ["development", "test"])
def test_local_docs_are_available(mode: str) -> None:
    settings = Settings.from_environ(environment(APP_ENV=mode))
    assert settings.api_docs_enabled is True


@pytest.mark.parametrize("overrides", [
    {"APP_ENV": "prod"}, {"APP_ENV": ""}, {"JWT_ALGORITHM": "none"},
    {"JWT_ALGORITHM": "HS512"}, {"JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "0"},
    {"JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "-1"}, {"JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "x"},
    {"API_DOCS_ENABLED": "maybe"},
])
def test_invalid_configuration_fails_safely(overrides: dict[str, str]) -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_environ(environment(**overrides))


def test_explicit_docs_and_expiry_policy() -> None:
    settings = Settings.from_environ(environment(API_DOCS_ENABLED="true", JWT_ACCESS_TOKEN_EXPIRE_MINUTES="90"))
    assert settings.api_docs_enabled
    assert settings.jwt_access_token_expire_minutes == 90


def child_env(**overrides: str) -> dict[str, str]:
    # Do not inherit application/provider credentials from the invoking shell.
    allowed = {"PATH", "SYSTEMROOT", "TMPDIR"}
    env = {k: v for k, v in os.environ.items() if k in allowed}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT), DATABASE_URL="sqlite:///:memory:",
               RATE_LIMIT_REDIS_URL="redis://127.0.0.1:1/0", RATE_LIMIT_HMAC_KEY=secrets.token_urlsafe(48))
    env.update(overrides)
    return env


@pytest.mark.parametrize("value", [None, "", PUBLIC_OLD_DEFAULT, "a" * 64])
def test_application_import_fails_closed_in_production(value: str | None) -> None:
    env = child_env(APP_ENV="production")
    if value is not None:
        env["JWT_SECRET_KEY"] = value
    result = subprocess.run([sys.executable, "-c", "import app.main"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr
    if value:
        assert value not in result.stdout + result.stderr


@pytest.mark.parametrize("mode,docs", [("development", True), ("test", True), ("production", False)])
def test_real_application_docs_policy(mode: str, docs: bool) -> None:
    source = """
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
for path in ['/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect']:
    assert client.get(path).status_code == EXPECTED
assert client.get('/health').json() == {'status': 'ok'}
assert client.get('/auth/me').status_code == 401
assert app.debug is False
""".replace("EXPECTED", "200" if docs else "404")
    result = subprocess.run([sys.executable, "-c", source], cwd=ROOT, env=child_env(APP_ENV=mode, JWT_SECRET_KEY=secrets.token_urlsafe(48)), capture_output=True, text=True)
    assert result.returncode == 0, "Isolated docs/auth policy check failed (output suppressed)"


def test_no_implicit_dotenv_loading(tmp_path: Path) -> None:
    (tmp_path / '.env').write_text('APP_ENV=development\nJWT_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n')
    result = subprocess.run([sys.executable, "-c", "import app.main"], cwd=tmp_path, env=child_env(), capture_output=True, text=True)
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr


@pytest.mark.parametrize("process_wins", [False, True])
def test_uvicorn_explicit_env_file_loading(tmp_path: Path, process_wins: bool) -> None:
    # Use Uvicorn's actual loader, but never start a server or contact a provider.
    fixture_secret = secrets.token_urlsafe(48)
    file = tmp_path / '.env'
    file.write_text('APP_ENV=development\nJWT_SECRET_KEY=' + fixture_secret + '\nAPI_DOCS_ENABLED=true\n')
    env = child_env()
    if process_wins:
        env.update(APP_ENV='production', JWT_SECRET_KEY=secrets.token_urlsafe(48), API_DOCS_ENABLED='false')
    source = """
import os, sys
from uvicorn import Config
original = os.environ.get('JWT_SECRET_KEY')
config = Config('app.main:app', env_file=sys.argv[1], log_config=None)
from app.core.config import SETTINGS
assert SETTINGS.app_env == sys.argv[2]
assert SETTINGS.api_docs_enabled == (sys.argv[2] == 'development')
if original is not None:
    assert SETTINGS.jwt_secret_key == original
else:
    from dotenv import dotenv_values
    assert SETTINGS.jwt_secret_key == dotenv_values(sys.argv[1])['JWT_SECRET_KEY']
"""
    result = subprocess.run([sys.executable, '-c', source, str(file), 'production' if process_wins else 'development'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, "Explicit env-file/precedence check failed (output suppressed)"
    assert fixture_secret not in result.stdout + result.stderr


def test_environment_variants_ignored_and_templates_preserved() -> None:
    for path in ['.env', '.env.local', '.env.production', '.env.production.local', 'nested/.env.staging', '.envrc']:
        result = subprocess.run(['git', 'check-ignore', '--no-index', path], cwd=ROOT, capture_output=True)
        assert result.returncode == 0
    for path in ['.env.example', '.env.production.example', 'nested/.env.example']:
        result = subprocess.run(['git', 'check-ignore', '--no-index', path], cwd=ROOT, capture_output=True)
        assert result.returncode == 1


def test_postgres_engine_has_bounded_pool_and_health_checks() -> None:
    from app.db.database import create_app_engine

    # Engine construction does not connect to this synthetic endpoint.
    engine = create_app_engine("postgresql+psycopg://synthetic:synthetic@127.0.0.1/dabbarha")
    try:
        assert engine.pool.size() == 5
        assert engine.pool._max_overflow == 2
        assert engine.pool._timeout == 10
        assert engine.pool._recycle == 1800
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()
