"""Fail-closed notification settings; no automatic dotenv or provider setup."""
from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass, field
from typing import Mapping

from app.core.settings import ConfigurationError, _boolean


@dataclass(frozen=True, repr=False)
class NotificationSettings:
    enabled: bool = False
    delivery_enabled: bool = False
    token_key: bytes = field(default=b"")
    token_key_id: str = "v1"
    expo_access_token: str = ""
    worker_poll_seconds: int = 5
    worker_batch_size: int = 50
    max_attempts: int = 5
    receipt_max_attempts: int = 8
    receipt_after_seconds: int = 900
    receipt_retention_seconds: int = 86400
    lease_seconds: int = 120
    stale_send_seconds: int = 300

    @classmethod
    def from_environ(cls, mode: str, environ: Mapping[str, str] | None = None) -> "NotificationSettings":
        env = os.environ if environ is None else environ
        enabled = _boolean(env, "NOTIFICATIONS_ENABLED", False)
        delivery = _boolean(env, "NOTIFICATION_DELIVERY_ENABLED", False)
        if enabled and not _boolean(env, "SESSION_AUTH_ENABLED", False):
            raise ConfigurationError("SESSION_AUTH_ENABLED=true is required to bind push tokens to revocable device sessions.")
        key = b""
        key_id = env.get("PUSH_TOKEN_ENCRYPTION_KEY_ID", "v1")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", key_id):
            raise ConfigurationError("PUSH_TOKEN_ENCRYPTION_KEY_ID must be 1–32 ASCII letters, digits, underscores or hyphens.")
        if enabled or delivery:
            encoded = env.get("PUSH_TOKEN_ENCRYPTION_KEY", "")
            try:
                key = base64.b64decode(encoded, validate=True)
                if len(key) != 32 or len(set(key)) < 12:
                    raise ValueError()
                session_key = base64.b64decode(env.get("SESSION_RECEIPT_KEY", ""), validate=True) if env.get("SESSION_RECEIPT_KEY") else b""
                if key in {env.get("JWT_SECRET_KEY", "").encode(), env.get("RATE_LIMIT_HMAC_KEY", "").encode(), session_key}:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ConfigurationError("PUSH_TOKEN_ENCRYPTION_KEY requires a separate securely random 32-byte base64 key.") from None
        if delivery and not enabled:
            raise ConfigurationError("NOTIFICATION_DELIVERY_ENABLED requires NOTIFICATIONS_ENABLED=true.")
        if delivery and mode != "production" and env.get("NOTIFICATION_PROVIDER", "") != "mock":
            raise ConfigurationError("Development delivery requires NOTIFICATION_PROVIDER=mock; real push delivery is production-only.")
        if delivery and mode == "production" and env.get("NOTIFICATION_PROVIDER", "expo") != "expo":
            raise ConfigurationError("Production notification delivery requires the Expo provider adapter.")
        access_token = env.get("EXPO_PUSH_ACCESS_TOKEN", "")
        if "\n" in access_token or "\r" in access_token:
            raise ConfigurationError("EXPO_PUSH_ACCESS_TOKEN must be a single-line value.")
        values = {}
        for field_name, env_name, default, maximum in (
            ("worker_poll_seconds", "NOTIFICATION_WORKER_POLL_SECONDS", 5, 300),
            ("worker_batch_size", "NOTIFICATION_WORKER_BATCH_SIZE", 50, 500),
            ("max_attempts", "NOTIFICATION_MAX_ATTEMPTS", 5, 10),
            ("receipt_max_attempts", "NOTIFICATION_RECEIPT_MAX_ATTEMPTS", 8, 20),
            ("receipt_after_seconds", "NOTIFICATION_RECEIPT_AFTER_SECONDS", 900, 86400),
            ("receipt_retention_seconds", "NOTIFICATION_RECEIPT_RETENTION_SECONDS", 86400, 604800),
            ("lease_seconds", "NOTIFICATION_LEASE_SECONDS", 120, 3600),
            ("stale_send_seconds", "NOTIFICATION_STALE_SEND_SECONDS", 300, 3600),
        ):
            try:
                number = int(env.get(env_name, str(default)))
                if not 1 <= number <= maximum:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ConfigurationError(f"{env_name} must be an integer from 1 to {maximum}.") from None
            values[field_name] = number
        return cls(enabled=enabled, delivery_enabled=delivery, token_key=key,
                   token_key_id=key_id, expo_access_token=access_token, **values)
