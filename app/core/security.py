from datetime import datetime, timedelta, timezone
from typing import Any

import secrets

import jwt
from pwdlib import PasswordHash

from app.core.config import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)

password_hash = PasswordHash.recommended()
# Random process-held dummy material; never persisted or logged. Matches real Argon2 parameters.
DUMMY_PASSWORD_HASH = password_hash.hash(secrets.token_urlsafe(48))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, password_hash_value: str) -> bool:
    return password_hash.verify(plain_password, password_hash_value)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": subject, "exp": expires_at}

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except (OverflowError, TypeError, ValueError):
        raise jwt.InvalidTokenError("Invalid access claims") from None

    # Any new-protocol marker requires the entire v2 claim set; no legacy fallback.
    if any(key in payload for key in ("ver", "sid", "jti", "token_use", "iat")):
        from uuid import UUID
        try:
            if (type(payload.get("ver")) is not int or payload["ver"] != 2
                or payload.get("token_use") not in {"access", "admin_stepup"} or type(payload.get("iat")) is not int
                or type(payload.get("exp")) is not int or payload["iat"] >= payload["exp"]
                or str(UUID(payload["sid"])) != payload["sid"]
                or str(UUID(payload["jti"])) != payload["jti"]):
                raise ValueError()
            if payload.get("token_use") == "admin_stepup":
                if (payload.get("admin_role") not in {"admin", "superadmin"}
                    or type(payload.get("admin_mfa_at")) is not int
                    or payload["admin_mfa_at"] != payload["iat"]):
                    raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise jwt.InvalidTokenError("Invalid session access claims") from None
    return payload
