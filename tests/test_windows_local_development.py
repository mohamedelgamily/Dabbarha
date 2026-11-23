import base64
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys

import pytest

from scripts import local_windows_config as local


REPO = Path(__file__).resolve().parents[1]


def _secrets() -> tuple[str, str]:
    return secrets.token_urlsafe(48), base64.b64encode(secrets.token_bytes(32)).decode()


def _root(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".git").mkdir()
    shutil.copy(REPO / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(REPO / "alembic", tmp_path / "alembic")
    return tmp_path


def test_bootstrap_generates_persistent_valid_secrets_without_returning_them(tmp_path, capsys):
    root = _root(tmp_path)
    path, changed = local.ensure_local_config(root)
    first = path.read_text()
    values = local.load_local_config(root)[1]

    assert changed is True
    assert values["APP_ENV"] == "development"
    assert values["SESSION_AUTH_ENABLED"] == "true"
    assert values["RATE_LIMIT_BACKEND"] == "memory"
    assert len(values["JWT_SECRET_KEY"].encode()) >= 32
    assert len(base64.b64decode(values["SESSION_RECEIPT_KEY"], validate=True)) == 32
    assert values["JWT_SECRET_KEY"] not in capsys.readouterr().out

    _, changed_again = local.ensure_local_config(root)
    assert changed_again is False
    assert path.read_text() == first


def test_bootstrap_preserves_existing_valid_secrets_and_other_values(tmp_path):
    root = _root(tmp_path)
    jwt_secret, receipt = _secrets()
    path = root / ".env.local"
    path.write_text(
        f"APP_ENV=development\nDATABASE_URL=sqlite:///./existing.sqlite3\n"
        f"JWT_SECRET_KEY={jwt_secret}\nSESSION_AUTH_ENABLED=true\nSESSION_RECEIPT_KEY={receipt}\nCUSTOM_LOCAL_FLAG=kept\n"
    )

    local.ensure_local_config(root)
    values = local.load_local_config(root)[1]
    assert values["JWT_SECRET_KEY"] == jwt_secret
    assert values["SESSION_RECEIPT_KEY"] == receipt
    assert values["CUSTOM_LOCAL_FLAG"] == "kept"
    assert values["DATABASE_URL"] == "sqlite:///./existing.sqlite3"


def test_command_line_helper_loads_project_settings_and_never_prints_generated_secrets(tmp_path):
    root = _root(tmp_path)
    helper = REPO / "scripts" / "local_windows_config.py"
    created = subprocess.run(
        [sys.executable, str(helper), "ensure", "--root", str(root)],
        check=False, text=True, capture_output=True,
    )
    assert created.returncode == 0, created.stderr
    secrets_in_file = local.load_local_config(root)[1]
    assert secrets_in_file["JWT_SECRET_KEY"] not in created.stdout + created.stderr
    assert secrets_in_file["SESSION_RECEIPT_KEY"] not in created.stdout + created.stderr

    validated = subprocess.run(
        [sys.executable, str(helper), "validate", "--root", str(root)],
        check=False, text=True, capture_output=True,
    )
    assert validated.returncode == 0


@pytest.mark.parametrize("entry", [
    "JWT_SECRET_KEY=changeme",
    "JWT_SECRET_KEY=",
    "SESSION_AUTH_ENABLED=false",
    "APP_ENV=production",
    "DATABASE_URL=postgresql://user:password@example.invalid/db",
    "DATABASE_URL=sqlite:////tmp/shared.sqlite3",
])
def test_bootstrap_rejects_invalid_existing_configuration_without_rewriting(tmp_path, entry):
    root = _root(tmp_path)
    path = root / ".env.local"
    original = f"APP_ENV=development\n{entry}\n"
    path.write_text(original)
    with pytest.raises(local.LocalSetupError):
        local.ensure_local_config(root)
    assert path.read_text() == original


def test_duplicate_keys_and_symlink_are_rejected(tmp_path, monkeypatch):
    root = _root(tmp_path)
    path = root / ".env.local"
    path.write_text("APP_ENV=development\nAPP_ENV=development\n")
    with pytest.raises(local.LocalSetupError, match="Duplicate"):
        local.ensure_local_config(root)

    path.unlink()
    target = root / "elsewhere"
    target.write_text("not a config")
    # Windows can require Developer Mode or elevation to create real symlinks.
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == path)
    with pytest.raises(local.LocalSetupError, match="symbolic link"):
        local.load_local_config(root)


def test_read_only_migration_status_does_not_create_missing_database(tmp_path):
    root = _root(tmp_path)
    local.ensure_local_config(root)
    database, applied, heads = local.migration_status(root)
    assert database == root / "dabbarha.db"
    assert applied == ()
    assert heads
    assert not database.exists()
    revisions = {path.stem.split("_")[0] for path in (root / "alembic" / "versions").glob("*.py")}
    assert "6b6a00000001" in revisions
    assert heads == ("2f3a00000001",)


def test_migration_status_refuses_unversioned_database_with_application_tables(tmp_path):
    root = _root(tmp_path)
    local.ensure_local_config(root)
    database = root / "dabbarha.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with pytest.raises(local.LocalSetupError, match="no Alembic revision marker"):
        local.migration_status(root)


def test_migration_status_refuses_unknown_or_newer_revision(tmp_path):
    root = _root(tmp_path)
    local.ensure_local_config(root)
    with sqlite3.connect(root / "dabbarha.db") as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('future-revision')")
    with pytest.raises(local.LocalSetupError, match="unknown or newer"):
        local.migration_status(root)


def test_explicit_migration_runs_from_validated_repository_root(tmp_path, monkeypatch):
    root = _root(tmp_path / "backend")
    local.ensure_local_config(root)
    outside = tmp_path / "other-working-directory"
    outside.mkdir()
    monkeypatch.chdir(outside)
    # Use real application imports and the complete migration chain on disposable SQLite.
    shutil.copytree(REPO / "app", root / "app")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///unrelated.db")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "APPLY")

    local.apply_local_migrations(root)

    database, applied, expected = local.migration_status(root)
    assert applied == expected == ("2f3a00000001",)
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert {"auth_sessions", "auth_refresh_tokens", "legacy_access_revocations"} <= tables
    assert Path.cwd() == outside
    assert not (outside / "dabbarha.db").exists()
    assert not (root / "unrelated.db").exists()


def test_migration_refuses_changed_database_after_confirmation(tmp_path, monkeypatch):
    root = _root(tmp_path)
    local.ensure_local_config(root)
    database = root / "dabbarha.db"

    def replace_target(_prompt):
        database.write_bytes(b"new target")
        return "APPLY"

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", replace_target)
    with pytest.raises(local.LocalSetupError, match="target changed"):
        local.apply_local_migrations(root)
    assert database.read_bytes() == b"new target"


def test_child_environment_uses_only_validated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///unrelated.db")
    monkeypatch.setenv("ADMIN_API_ENABLED", "true")
    monkeypatch.setenv("UVICORN_HOST", "0.0.0.0")
    env = local._child_environment({"APP_ENV": "development", "DATABASE_URL": "sqlite:///./dabbarha.db"})
    assert env["DATABASE_URL"] == "sqlite:///./dabbarha.db"
    assert "ADMIN_API_ENABLED" not in env
    assert "UVICORN_HOST" not in env


@pytest.mark.parametrize("entry", ["DATABASE_URL=${DATABASE_URL}", "jwt_secret_key=value", "DATABASE_URL"])
def test_bootstrap_rejects_ambiguous_dotenv_without_writing(tmp_path, entry):
    root = _root(tmp_path)
    config = root / ".env.local"
    config.write_text(entry)
    with pytest.raises(local.LocalSetupError):
        local.ensure_local_config(root)
    assert config.read_text() == entry


def test_git_ignores_local_secret_file_but_keeps_templates_trackable():
    def ignored(name):
        return subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", name], cwd=REPO,
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0

    assert ignored(".env.local")
    assert not ignored(".env.example")
    assert not ignored(".env.production.example")


def test_windows_scripts_keep_loopback_default_and_require_explicit_lan_mode():
    setup = (REPO / "scripts" / "setup-local-windows.ps1").read_text()
    start = (REPO / "scripts" / "start-local-windows.ps1").read_text()
    assert ".venv\\Scripts\\python.exe" in setup
    assert "pip check" in setup
    assert "check-ignore" in setup
    assert "redis-check" in setup and "migration-status" in setup
    assert "127.0.0.1" in start and "$ListenOnLan" in start
    assert "0.0.0.0" in start
    assert "serve --root $repoRoot" in start
    assert "New-NetFirewallRule" not in start
    assert "192.168.100.7" not in start
    assert "$ApplyMigrations" in start and "apply-migrations" in start


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows file ACLs")
def test_native_windows_acl_policy():
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
         str(REPO / "tests" / "windows-local-acl.tests.ps1")],
        check=True,
    )
