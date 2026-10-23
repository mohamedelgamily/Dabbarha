"""The notification process consumes runtime settings, never API signing keys."""
import base64
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import signal

import pytest

from app.core.notification_settings import NotificationSettings
from app.core.settings import ConfigurationError, RuntimeSettings, Settings

ROOT = Path(__file__).resolve().parents[1]


def _worker_environment(**overrides):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "APP_ENV": "test",
        "DATABASE_URL": "sqlite:///:memory:",
        "NOTIFICATIONS_ENABLED": "false",
        "NOTIFICATION_DELIVERY_ENABLED": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(overrides)
    return env


def test_standalone_worker_runs_without_jwt_secret():
    env = _worker_environment()
    result = subprocess.run([sys.executable, "-m", "app.commands.notification_worker", "--once"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert "notification_worker_disabled" in result.stderr
    assert "JWT_SECRET_KEY" not in result.stdout + result.stderr


@pytest.mark.parametrize("overrides,expected", [
    ({"APP_ENV": "unknown"}, "APP_ENV"),
    ({"DATABASE_URL": ""}, "DATABASE_URL"),
])
def test_worker_rejects_invalid_runtime_configuration_without_jwt(overrides, expected):
    result = subprocess.run([sys.executable, "-m", "app.commands.notification_worker", "--once"],
                            cwd=ROOT, env=_worker_environment(**overrides),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert expected in result.stderr
    assert "JWT_SECRET_KEY" not in result.stderr


def test_api_still_rejects_missing_jwt_secret():
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"], cwd=ROOT,
        env=_worker_environment(APP_ENV="production", API_DOCS_ENABLED="false"),
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr


def test_notification_encryption_configuration_does_not_require_jwt():
    env = {
        "NOTIFICATIONS_ENABLED": "true",
        "NOTIFICATION_DELIVERY_ENABLED": "true",
        "NOTIFICATION_PROVIDER": "expo",
        "SESSION_AUTH_ENABLED": "true",
        "PUSH_TOKEN_ENCRYPTION_KEY": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    }
    settings = NotificationSettings.from_environ("production", env)
    assert settings.enabled and settings.delivery_enabled and len(settings.token_key) == 32
    assert "JWT_SECRET_KEY" not in repr(settings)


def test_worker_recovers_after_cycle_failure_without_logging_error_text(monkeypatch, caplog):
    import app.commands.notification_worker as worker

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["notification_worker"])
    configured = NotificationSettings(enabled=True, delivery_enabled=False, worker_poll_seconds=5)
    monkeypatch.setattr(NotificationSettings, "from_environ", classmethod(lambda _cls, mode: configured))

    class Engine:
        def dispose(self):
            pass

    class Provider:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(worker, "create_app_engine", lambda *_args, **_kwargs: Engine())
    monkeypatch.setattr(worker, "ExpoPushAdapter", Provider)
    registered = {}
    monkeypatch.setattr(worker.signal, "signal", lambda signum, handler: registered.__setitem__(signum, handler))
    calls = []

    def run_cycle(*_args):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("synthetic-private-database-detail")
        return {"scheduled": 0, "deliveries": 0, "receipts": 0}

    monkeypatch.setattr(worker, "run_once", run_cycle)

    def sleep(_seconds):
        registered[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(worker.time, "sleep", sleep)
    with caplog.at_level(logging.ERROR):
        assert worker.main() == 0
    assert len(calls) == 2
    assert "notification_worker_cycle_failed error_type=RuntimeError" in caplog.text
    assert "synthetic-private-database-detail" not in caplog.text


def test_runtime_settings_exclude_authentication_material():
    runtime = RuntimeSettings.from_environ({"APP_ENV": "production", "DATABASE_URL": "sqlite:///:memory:"})
    assert runtime.app_env == "production"
    with pytest.raises(ConfigurationError):
        Settings.from_environ({"APP_ENV": "production", "DATABASE_URL": "sqlite:///:memory:"})
