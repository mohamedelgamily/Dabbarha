"""Validated abuse-protection policy, separate from the existing JWT contract."""
from dataclasses import dataclass, field
import ipaddress
import math
import os
import secrets
from typing import Mapping
from urllib.parse import urlsplit

from app.core.settings import ConfigurationError, _jwt_secret


@dataclass(frozen=True, repr=False)
class APISecuritySettings:
    backend: str = "memory"
    redis_url: str = ""
    hmac_key: bytes = field(default_factory=lambda: secrets.token_bytes(48))
    login_limit: int = 5
    login_ip_limit: int = 30
    login_window: int = 900
    registration_limit: int = 5
    registration_window: int = 3600
    write_limit: int = 60
    read_limit: int = 120
    forecast_limit: int = 30
    affordability_limit: int = 10
    admin_limit: int = 60
    admin_ip_limit: int = 120
    financial_window: int = 60
    body_bytes: int = 65536
    json_depth: int = 64
    body_timeout: float = 10.0
    argon_concurrency: int = 2
    argon_wait: float = 0.25
    redis_timeout: float = 1.0

    @classmethod
    def from_environ(cls, mode: str, environ: Mapping[str, str] | None = None) -> "APISecuritySettings":
        env = os.environ if environ is None else environ
        backend = env.get("RATE_LIMIT_BACKEND", "redis" if mode == "production" else "memory")
        if backend not in {"redis", "memory"} or (mode == "production" and backend != "redis"):
            raise ConfigurationError("RATE_LIMIT_BACKEND must be redis in production; memory is development/test only.")
        key = env.get("RATE_LIMIT_HMAC_KEY", "")
        if backend == "redis" or key:
            try:
                _jwt_secret({"JWT_SECRET_KEY": key})
            except ConfigurationError:
                raise ConfigurationError("RATE_LIMIT_HMAC_KEY requires explicit securely generated, non-placeholder secret material (at least 32 bytes).") from None
            if key == env.get("JWT_SECRET_KEY"):
                raise ConfigurationError("RATE_LIMIT_HMAC_KEY must be separate from JWT_SECRET_KEY.")
        url = env.get("RATE_LIMIT_REDIS_URL", "")
        if backend == "redis":
            try:
                parsed = urlsplit(url)
                valid = not parsed.query and not parsed.fragment
                if parsed.scheme == "unix":
                    valid = valid and not parsed.netloc and parsed.path.startswith("/") and len(parsed.path) > 1
                else:
                    host = parsed.hostname
                    address = ipaddress.ip_address(host) if host != "localhost" else None
                    valid = valid and parsed.scheme in {"redis", "rediss"} and (
                        host == "localhost" or (
                            address is not None and (address.is_loopback or (address.is_private
                            and not address.is_unspecified and not address.is_multicast and not address.is_reserved))
                        )
                    ) and (parsed.port is None or 1 <= parsed.port <= 65535)
                    valid = valid and (not parsed.path or parsed.path[1:].isdigit())
                if not valid:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ConfigurationError("RATE_LIMIT_REDIS_URL must use a private literal IP/localhost or an absolute unix socket, without query options.") from None
        integers = {
            "login_limit": ("RATE_LIMIT_LOGIN", 5, 100000),
            "login_ip_limit": ("RATE_LIMIT_LOGIN_IP", 30, 100000),
            "login_window": ("RATE_LIMIT_LOGIN_WINDOW_SECONDS", 900, 604800),
            "registration_limit": ("RATE_LIMIT_REGISTRATION", 5, 100000),
            "registration_window": ("RATE_LIMIT_REGISTRATION_WINDOW_SECONDS", 3600, 604800),
            "write_limit": ("RATE_LIMIT_WRITES", 60, 100000),
            "read_limit": ("RATE_LIMIT_READS", 120, 100000),
            "forecast_limit": ("RATE_LIMIT_FORECAST", 30, 100000),
            "affordability_limit": ("RATE_LIMIT_AFFORDABILITY", 10, 100000),
            "admin_limit": ("RATE_LIMIT_ADMIN", 60, 100000),
            "admin_ip_limit": ("RATE_LIMIT_ADMIN_IP", 120, 100000),
            "financial_window": ("RATE_LIMIT_FINANCIAL_WINDOW_SECONDS", 60, 604800),
            "body_bytes": ("API_MAX_BODY_BYTES", 65536, 1048576),
            "json_depth": ("API_MAX_JSON_DEPTH", 64, 128),
            "argon_concurrency": ("AUTH_ARGON2_CONCURRENCY", 2, 32),
        }
        values = {}
        for field_name, (name, default, maximum) in integers.items():
            try:
                value = int(env.get(name, str(default)))
                if not 1 <= value <= maximum:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ConfigurationError(f"{name} must be an integer from 1 to {maximum}.") from None
            values[field_name] = value
        for field_name, name, default, maximum in [
            ("body_timeout", "API_BODY_TIMEOUT_SECONDS", 10, 300),
            ("argon_wait", "AUTH_ARGON2_WAIT_SECONDS", .25, 5),
            ("redis_timeout", "RATE_LIMIT_REDIS_TIMEOUT_SECONDS", 1, 5),
        ]:
            try:
                value = float(env.get(name, str(default)))
                if not math.isfinite(value) or not 0 < value <= maximum:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ConfigurationError(f"{name} must be finite, positive and at most {maximum} seconds.") from None
            values[field_name] = value
        return cls(backend=backend, redis_url=url,
                   hmac_key=key.encode() if key else secrets.token_bytes(48), **values)
