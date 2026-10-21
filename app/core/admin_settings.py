"""Default-off administrator MFA policy with a separate TOTP-at-rest key."""
import base64
import os
import re
from dataclasses import dataclass
from typing import Mapping

from app.core.settings import ConfigurationError, _boolean


def decode_totp_encryption_key(env: Mapping[str, str]) -> bytes:
    try:
        encoded = env.get("ADMIN_TOTP_ENCRYPTION_KEY", "")
        key = base64.b64decode(encoded, validate=True)
        if (len(key) != 32 or len(set(key)) < 12
            or encoded in {env.get("JWT_SECRET_KEY"), env.get("RATE_LIMIT_HMAC_KEY"),
                           env.get("SESSION_RECEIPT_KEY")}
            or key in {env.get("JWT_SECRET_KEY", "").encode(),
                       env.get("RATE_LIMIT_HMAC_KEY", "").encode()}):
            raise ValueError()
        return key
    except (ValueError, TypeError):
        raise ConfigurationError("ADMIN_TOTP_ENCRYPTION_KEY requires a separate, securely generated 32-byte base64 key.") from None


@dataclass(frozen=True, repr=False)
class AdminSettings:
    enabled: bool = False
    totp_encryption_key: bytes = b""
    totp_key_id: str = "v1"
    stepup_minutes: int = 5
    max_stepup_age_seconds: int = 300

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> "AdminSettings":
        env = os.environ if environ is None else environ
        enabled = _boolean(env, "ADMIN_API_ENABLED", False)
        key = decode_totp_encryption_key(env) if enabled else b""
        if enabled:
            if _boolean(env, "SESSION_AUTH_ENABLED", False) is not True:
                raise ConfigurationError("ADMIN_API_ENABLED requires SESSION_AUTH_ENABLED=true for revocable v2 sessions.")
            if _boolean(env, "SESSION_LEGACY_ISSUANCE", True):
                raise ConfigurationError("ADMIN_API_ENABLED requires SESSION_LEGACY_ISSUANCE=false.")
        kid = env.get("ADMIN_TOTP_KEY_ID", "v1")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", kid):
            raise ConfigurationError("ADMIN_TOTP_KEY_ID must be 1–32 ASCII letters, digits, underscores or hyphens.")
        try:
            minutes = int(env.get("ADMIN_STEPUP_TOKEN_MINUTES", "5"))
            if not 1 <= minutes <= 15:
                raise ValueError()
        except (ValueError, TypeError):
            raise ConfigurationError("ADMIN_STEPUP_TOKEN_MINUTES must be from 1 to 15.") from None
        return cls(enabled=enabled, totp_encryption_key=key, totp_key_id=kid,
                   stepup_minutes=minutes, max_stepup_age_seconds=minutes * 60)
