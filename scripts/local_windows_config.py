"""Safe local Windows configuration helper; values are never printed."""
from __future__ import annotations

import argparse
import base64
import io
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
from contextlib import closing


DEFAULTS = {
    "APP_ENV": "development",
    "DATABASE_URL": "sqlite:///./dabbarha.db",
    "JWT_ALGORITHM": "HS256",
    "SESSION_AUTH_ENABLED": "true",
    "SESSION_RECEIPT_KEY_ID": "v1",
    "RATE_LIMIT_BACKEND": "memory",
    "API_DOCS_ENABLED": "true",
    "NOTIFICATIONS_ENABLED": "false",
    "NOTIFICATION_DELIVERY_ENABLED": "false",
}
_SETTING_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
_SETTINGS_PREFIXES = (
    "APP_", "DATABASE_", "JWT_", "SESSION_", "RATE_LIMIT_", "API_",
    "AUTH_", "ADMIN_", "NOTIFICATION", "PUSH_", "EXPO_",
)
_SYSTEM_NAMES = {
    "SYSTEMROOT", "WINDIR", "PATH", "SYSTEMDRIVE", "COMSPEC", "USERPROFILE",
    "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "TMPDIR", "HOME",
}


class LocalSetupError(ValueError):
    """A safe setup error without environment values or database credentials."""


def _root(path: str | Path) -> Path:
    root = Path(path).resolve()
    if not (root / ".git").exists() or not (root / "alembic.ini").is_file():
        raise LocalSetupError("The selected folder is not the Dabbarha backend repository root.")
    return root


def _config_file(root: Path, path: str | Path | None) -> Path:
    expected = root / ".env.local"
    raw = Path(path) if path else expected
    if not raw.is_absolute():
        raw = root / raw
    # Check the final path before resolving it: resolving first would hide links.
    if raw.is_symlink() or raw.is_junction():
        raise LocalSetupError("Refusing to follow a symbolic link for .env.local.")
    if raw.exists() and (not raw.is_file() or raw.stat().st_nlink != 1):
        raise LocalSetupError(".env.local must be an ordinary, unlinked file.")
    selected = raw.resolve()
    if selected != expected.resolve():
        raise LocalSetupError("Local setup only manages the ignored repository-root .env.local file.")
    return selected


def _read_values(path: Path) -> tuple[dict[str, str], str]:
    try:
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        from dotenv.parser import parse_stream

        values = {}
        for binding in parse_stream(io.StringIO(content)):
            if binding.error:
                raise LocalSetupError("Invalid dotenv syntax in .env.local.")
            if binding.key is None:
                continue
            if (not _SETTING_NAME.fullmatch(binding.key) or binding.value is None
                    or "${" in binding.value or "\x00" in binding.value):
                raise LocalSetupError("Use uppercase dotenv assignments with literal values in .env.local.")
            if binding.key in values:
                raise LocalSetupError("Duplicate setting in .env.local.")
            values[binding.key] = binding.value
        return values, content
    except (OSError, UnicodeError):
        raise LocalSetupError("Could not safely read .env.local.") from None


def _local_sqlite_path(root: Path, database_url: str) -> Path:
    try:
        from sqlalchemy.engine import make_url

        url = make_url(database_url)
    except Exception:
        raise LocalSetupError("DATABASE_URL is invalid; use a repository-local SQLite development database.") from None
    if url.drivername not in {"sqlite", "sqlite+pysqlite"} or not url.database or url.database == ":memory:":
        raise LocalSetupError(
            "The Windows helper supports a persistent SQLite file inside this repository only. "
            "It will not inspect or migrate a shared or remote database."
        )
    if url.query or any((url.username, url.password, url.host, url.port)):
        raise LocalSetupError("SQLite URI/query options are not accepted by the local Windows helper.")
    database = Path(url.database)
    if not database.is_absolute():
        database = root / database
    resolved = database.resolve()
    if not resolved.is_relative_to(root):
        raise LocalSetupError("The SQLite file must be inside the repository.")
    if (database.is_symlink() or database.is_junction()
            or (resolved.exists() and (not resolved.is_file() or resolved.stat().st_nlink != 1))
            or ".git" in resolved.relative_to(root).parts):
        raise LocalSetupError("Use an ordinary, unlinked SQLite file inside the repository.")
    if resolved == root:
        raise LocalSetupError("DATABASE_URL must identify a file, not the repository folder.")
    return resolved


def _validate(root: Path, values: dict[str, str]) -> Path:
    if values.get("APP_ENV") != "development":
        raise LocalSetupError("Local Windows setup requires APP_ENV=development; it never rewrites another mode.")
    if values.get("SESSION_AUTH_ENABLED", "").strip().lower() not in {"true", "1", "yes"}:
        raise LocalSetupError("Set SESSION_AUTH_ENABLED=true in .env.local to use V2 device sessions.")
    try:
        from app.core.settings import Settings
        from app.core.session_settings import SessionSettings
        from app.core.api_security_settings import APISecuritySettings

        Settings.from_environ(values)
        sessions = SessionSettings.from_environ(values)
        APISecuritySettings.from_environ("development", values)
    except Exception:
        # Keep this boundary value-free even if a future validator changes wording.
        raise LocalSetupError("Local settings validation failed. Check the setting names and rules in docs/windows-local-development.md.") from None
    if not sessions.enabled:
        raise LocalSetupError("V2 sessions are disabled; set SESSION_AUTH_ENABLED=true in .env.local.")
    return _local_sqlite_path(root, values.get("DATABASE_URL", ""))


def ensure_local_config(root_path: str | Path, config_path: str | Path | None = None) -> tuple[Path, bool]:
    """Create only missing local settings; preserve existing values and file contents."""
    root = _root(root_path)
    path = _config_file(root, config_path)
    lock = path.with_name(".env.local.setup-lock")
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise LocalSetupError("Another setup owns the local configuration lock.") from None
    try:
        with handle:
            return _ensure_locked(root, path)
    finally:
        lock.unlink()


def _ensure_locked(root: Path, path: Path) -> tuple[Path, bool]:
    values, original = _read_values(path)
    additions: list[tuple[str, str]] = []

    for key, value in DEFAULTS.items():
        if key not in values:
            values[key] = value
            additions.append((key, value))

    if "JWT_SECRET_KEY" not in values:
        values["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
        additions.append(("JWT_SECRET_KEY", values["JWT_SECRET_KEY"]))
    if "SESSION_RECEIPT_KEY" not in values:
        values["SESSION_RECEIPT_KEY"] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        additions.append(("SESSION_RECEIPT_KEY", values["SESSION_RECEIPT_KEY"]))
    if values.get("RATE_LIMIT_BACKEND") == "redis" and "RATE_LIMIT_HMAC_KEY" not in values:
        values["RATE_LIMIT_HMAC_KEY"] = secrets.token_urlsafe(48)
        additions.append(("RATE_LIMIT_HMAC_KEY", values["RATE_LIMIT_HMAC_KEY"]))

    _validate(root, values)
    if not additions:
        return path, False

    lines = [f"{key}={value}" for key, value in additions]
    # Exclusive create prevents a concurrent first run from replacing a file.
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines) + "\n")
        except FileExistsError:
            raise LocalSetupError(".env.local appeared during setup; rerun setup to validate it safely.") from None
    else:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            if original and not original.endswith(("\n", "\r")):
                handle.write("\n")
            handle.write("\n".join(lines) + "\n")
    _read_values(path)
    return path, True


def load_local_config(root_path: str | Path, config_path: str | Path | None = None) -> tuple[Path, dict[str, str]]:
    root = _root(root_path)
    path = _config_file(root, config_path)
    values, _ = _read_values(path)
    _validate(root, values)
    return path, values


def migration_status(root_path: str | Path, config_path: str | Path | None = None) -> tuple[Path, tuple[str, ...], tuple[str, ...]]:
    root = _root(root_path)
    _, values = load_local_config(root, config_path)
    return _migration_status(root, _local_sqlite_path(root, values["DATABASE_URL"]))


def _migration_status(root: Path, database: Path):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic").replace("%", "%%"))
    scripts = ScriptDirectory.from_config(config)
    expected = tuple(sorted(scripts.get_heads()))
    applied: tuple[str, ...] = ()
    if database.is_file():
        # Read-only SQLite URI: status checks never create or alter a DB file.
        uri = f"{database.as_uri()}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=2)) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
                ).fetchone()
                if exists:
                    applied = tuple(sorted(row[0] for row in connection.execute(
                        "SELECT version_num FROM alembic_version"
                    )))
                if not applied:
                    user_tables = connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
                    ).fetchall()
                    if user_tables:
                        raise LocalSetupError(
                            "The local SQLite database has application tables but no Alembic revision marker. "
                            "Startup will not guess its schema or migrate it; have its history inspected first."
                        )
        except LocalSetupError:
            raise
        except sqlite3.Error:
            raise LocalSetupError("Could not inspect the local SQLite migration version read-only.") from None
    history = {revision.revision for head in expected for revision in scripts.iterate_revisions(head, "base")}
    if not set(applied).issubset(history):
        raise LocalSetupError(
            "The local SQLite database has an unknown or newer Alembic revision. "
            "Startup will not attempt to migrate it with this checkout."
        )
    return database, applied, expected


def apply_local_migrations(root_path: str | Path, config_path: str | Path | None = None) -> None:
    root = _root(root_path)
    _, values = load_local_config(root, config_path)
    database = _local_sqlite_path(root, values["DATABASE_URL"])
    def identity():
        if not database.exists():
            return None
        stat = database.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    before = identity()
    _, applied, expected = _migration_status(root, database)
    if applied == expected:
        return
    if identity() != before:
        raise LocalSetupError("The SQLite target changed during inspection. Inspect it again.")
    if not sys.stdin.isatty():
        raise LocalSetupError("Local migration requires an interactive terminal.")
    print(f"Local SQLite target: {database}")
    print("Confirm ownership and back up any existing data before proceeding.")
    if input("Type APPLY to upgrade this file to Alembic head: ") != "APPLY":
        raise LocalSetupError("Migration was cancelled.")
    if _local_sqlite_path(root, values["DATABASE_URL"]) != database or identity() != before:
        raise LocalSetupError("The SQLite target changed during confirmation. Inspect it again.")
    from sqlalchemy.engine import URL

    url = URL.create("sqlite", database=str(database)).render_as_string()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root,
                   env=_child_environment({"APP_ENV": "development", "DATABASE_URL": url}),
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if _migration_status(root, database)[1:] != (expected, expected):
        raise LocalSetupError("Local database did not reach the expected Alembic head.")


def _child_environment(values: dict[str, str]) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in _SYSTEM_NAMES}
    env.update((key, value) for key, value in values.items() if key.startswith(_SETTINGS_PREFIXES))
    return env


def serve_local(root: Path, config_path: str, host: str, port: int) -> int:
    _, values = load_local_config(root, config_path)
    database = _local_sqlite_path(root, values["DATABASE_URL"])
    _, applied, expected = _migration_status(root, database)
    if applied != expected:
        raise LocalSetupError("Local migrations are pending. Inspect the database before using -ApplyMigrations.")
    from sqlalchemy.engine import URL

    values["DATABASE_URL"] = URL.create("sqlite", database=str(database)).render_as_string()
    return subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port),
         "--no-access-log", "--no-proxy-headers"],
        cwd=root, env=_child_environment(values),
    ).returncode


def check_redis(root_path: str | Path, config_path: str | Path | None = None) -> bool:
    _, values = load_local_config(root_path, config_path)
    settings = __import__("app.core.api_security_settings", fromlist=["APISecuritySettings"])
    policy = settings.APISecuritySettings.from_environ("development", values)
    if policy.backend == "memory":
        return False
    from app.core.rate_limit import RedisStore

    store = RedisStore(policy.redis_url, policy.redis_timeout, policy.redis_allowed_cidrs)
    try:
        store.ping()
    except Exception:
        raise LocalSetupError("Configured Redis is required but unavailable; check its local service and URL.") from None
    finally:
        store.close()
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("ensure", "validate", "migration-status", "apply-migrations", "redis-check", "serve", "check-config-path"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--file", default=".env.local")
    parser.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        root = _root(args.root)
        source_root = Path(__file__).resolve().parents[1]
        for import_root in (root, source_root):
            if str(import_root) not in sys.path:
                sys.path.insert(0, str(import_root))
        if args.command == "check-config-path":
            _config_file(root, args.file)
        elif args.command == "ensure":
            path, changed = ensure_local_config(root, args.file)
            print("Local development configuration created." if changed else "Local development configuration is already valid.")
            print("Secret values are not displayed.")
        elif args.command == "validate":
            load_local_config(root, args.file)
            print("Local settings are valid; secret values are not displayed.")
        elif args.command == "serve":
            return serve_local(root, args.file, args.host, args.port)
        elif args.command == "redis-check":
            required = check_redis(root, args.file)
            print("Configured Redis is reachable." if required else "Redis is not required: development uses the in-process rate limiter.")
        elif args.command == "migration-status":
            path, applied, expected = migration_status(root, args.file)
            print(f"Local SQLite database file: {path}")
            print(f"Applied Alembic revision(s): {', '.join(applied) if applied else '(none)'}")
            print(f"Expected Alembic head(s): {', '.join(expected)}")
            if applied != expected:
                print("MIGRATIONS_PENDING")
                return 3
            print("MIGRATIONS_CURRENT")
        elif args.command == "apply-migrations":
            apply_local_migrations(root, args.file)
            path, applied, expected = migration_status(root, args.file)
            if applied != expected:
                raise LocalSetupError("Local database did not reach the expected Alembic head.")
            print("Local migrations reached head; no data reset or downgrade was performed.")
        return 0
    except subprocess.CalledProcessError:
        print("Local Alembic upgrade failed. Check the local backup and migration state.", file=sys.stderr)
        return 2
    except LocalSetupError as exc:
        print(f"Local setup check failed: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("Local setup helper encountered an unexpected error; no configuration values were printed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
