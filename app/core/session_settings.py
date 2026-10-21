"""Explicit opt-in session policy. Never discover files or generate production keys."""
import base64
from dataclasses import dataclass
import os
import re
from typing import Mapping

from app.core.settings import ConfigurationError, _boolean


@dataclass(frozen=True, repr=False)
class SessionSettings:
    enabled: bool = False
    receipt_key: bytes = b""
    receipt_key_id: str = "v1"
    access_minutes: int = 15
    idle_days: int = 30
    absolute_days: int = 90
    recovery_seconds: int = 60
    recovery_retries: int = 2
    refresh_limit: int = 10
    refresh_ip_limit: int = 60
    lock_timeout_seconds: int = 5
    legacy_issuance: bool = True
    legacy_acceptance: bool = True

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None):
        env = os.environ if environ is None else environ
        enabled = _boolean(env, "SESSION_AUTH_ENABLED", False)
        key = b""
        if enabled:
            encoded = env.get("SESSION_RECEIPT_KEY", "")
            try:
                key = base64.b64decode(encoded, validate=True)
                if (len(key) != 32 or len(set(key)) < 12
                    or encoded in {env.get("JWT_SECRET_KEY"), env.get("RATE_LIMIT_HMAC_KEY")}
                    or key in {env.get("JWT_SECRET_KEY", "").encode(), env.get("RATE_LIMIT_HMAC_KEY", "").encode()}):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ConfigurationError("SESSION_RECEIPT_KEY requires a separate securely random 32-byte base64 key.") from None
        kid = env.get("SESSION_RECEIPT_KEY_ID", "v1")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", kid):
            raise ConfigurationError("SESSION_RECEIPT_KEY_ID must be 1–32 ASCII letters, digits, underscores or hyphens.")
        values = {}
        for field, name, default, maximum in [
            ("access_minutes", "SESSION_ACCESS_TOKEN_EXPIRE_MINUTES", 15, 60),
            ("idle_days", "SESSION_REFRESH_IDLE_DAYS", 30, 90),
            ("absolute_days", "SESSION_ABSOLUTE_DAYS", 90, 365),
            ("refresh_limit", "SESSION_REFRESH_LIMIT", 10, 100000),
            ("refresh_ip_limit", "SESSION_REFRESH_IP_LIMIT", 60, 100000),
            ("lock_timeout_seconds", "SESSION_DB_LOCK_TIMEOUT_SECONDS", 5, 30),
        ]:
            try:
                value = int(env.get(name, str(default)))
                if not 1 <= value <= maximum:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ConfigurationError(f"{name} must be an integer from 1 to {maximum}.") from None
            values[field] = value
        if values["idle_days"] > values["absolute_days"]:
            raise ConfigurationError("Session inactivity expiry cannot exceed absolute expiry.")
        return cls(enabled=enabled, receipt_key=key, receipt_key_id=kid, **values,
                   legacy_issuance=_boolean(env, "SESSION_LEGACY_ISSUANCE", True),
                   legacy_acceptance=_boolean(env, "SESSION_LEGACY_ACCEPTANCE", True))
