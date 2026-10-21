"""Validated process settings; environment files are loaded explicitly by Uvicorn.

No secret generation, file discovery, environment mutation or logging occurs here.
"""
from dataclasses import dataclass
import os
import re
from typing import Mapping


class ConfigurationError(ValueError):
    """Safe configuration error containing field names, never supplied values."""


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ConfigurationError(f"{name} must be true or false.")


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    try:
        value = int(env.get(name, str(default)))
    except (ValueError, TypeError):
        raise ConfigurationError(f"{name} must be an integer.") from None
    if value < minimum:
        raise ConfigurationError(f"{name} is below its allowed minimum.")
    return value


def _jwt_secret(env: Mapping[str, str]) -> str:
    secret = env.get("JWT_SECRET_KEY", "")
    normalized = re.sub(r"[^a-z0-9]", "", secret.lower())
    placeholders = (
        "developmentonlyinsecurejwtsecret", "changeme", "replaceme",
        "replacewith", "yoursecret", "yourjwtsecret", "placeholder",
        "examplesecret", "insertsecret", "setarealsecret", "changethis", "pleasechange",
    )
    # These checks reject obvious weak values; they cannot prove random entropy.
    repeated = bool(secret) and any(
        len(secret) % size == 0 and secret == secret[:size] * (len(secret) // size)
        for size in range(1, len(secret) // 2 + 1)
    )
    sequences = "0123456789abcdefghijklmnopqrstuvwxyz0123456789"
    if (
        len(secret.encode("utf-8")) < 32
        or secret != secret.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in secret)
        or (secret.startswith("<") and secret.endswith(">"))
        or (secret.startswith("{{") and secret.endswith("}}"))
        or len(set(secret)) < 12
        or repeated
        or normalized in sequences
        or any(marker in normalized for marker in placeholders)
    ):
        raise ConfigurationError(
            "JWT_SECRET_KEY must be explicitly configured with at least 32 UTF-8 bytes "
            "of securely generated, non-placeholder secret material; obvious weak values "
            "and surrounding whitespace/control characters are not accepted. See docs/configuration.md."
        )
    return secret  # Preserve exact bytes: do not trim, transform or rotate a key.


@dataclass(frozen=True, repr=False)
class Settings:
    # Do not expose credentials/database URLs through dataclass repr or validation errors.
    app_env: str
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    api_docs_enabled: bool

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        mode = env.get("APP_ENV", "production").strip().lower()
        if mode not in {"development", "test", "production"}:
            raise ConfigurationError("APP_ENV must be development, test or production.")
        secret = _jwt_secret(env)
        algorithm = env.get("JWT_ALGORITHM", "HS256")
        if algorithm != "HS256":
            raise ConfigurationError("JWT_ALGORITHM must be HS256 for this deployment contract.")
        database_url = env.get("DATABASE_URL", "sqlite:///./dabbarha.db")
        if not database_url.strip():
            raise ConfigurationError("DATABASE_URL cannot be empty.")
        return cls(
            app_env=mode,
            database_url=database_url,
            jwt_secret_key=secret,
            jwt_algorithm=algorithm,
            jwt_access_token_expire_minutes=_integer(env, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 60, 1),
            api_docs_enabled=_boolean(env, "API_DOCS_ENABLED", mode != "production"),
        )
