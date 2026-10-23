"""Runtime admission control; identities come only from the connection and auth context."""
from contextlib import contextmanager
import ipaddress
import threading

from fastapi import HTTPException, Request

from app.core.rate_limit import Limiter, MemoryStore, RedisStore


class SecurityRuntime:
    def __init__(self, settings):
        self.settings = settings
        from app.core.session_settings import SessionSettings
        self.session_policy = SessionSettings.from_environ()
        store = (RedisStore(settings.redis_url, settings.redis_timeout, settings.redis_allowed_cidrs)
                 if settings.backend == "redis" else MemoryStore())
        self.limiter = Limiter(store, settings.hmac_key)
        self.argon_slots = threading.BoundedSemaphore(settings.argon_concurrency)

    @contextmanager
    def password_slot(self):
        if not self.argon_slots.acquire(timeout=self.settings.argon_wait):
            raise HTTPException(503, "Authentication is temporarily busy. Please try again shortly.",
                                headers={"Retry-After": "1"})
        try:
            yield
        finally:
            self.argon_slots.release()

    def auth_ip(self, path: str, ip: str):
        s = self.settings
        if (path == "/auth/login" or path == "/auth/sessions" or path == "/auth/account"
            or path == "/admin/auth/step-up" or path.endswith("/revoke")):
            group, limit, window = "login_ip", s.login_ip_limit, s.login_window
        elif path == "/auth/register":
            group, limit, window = "registration", s.registration_limit, s.registration_window
        else:
            self.refresh_ip(ip)
            return
        self.limiter.reserve([self.limiter.rule(group, ip, limit, window)])

    def admin_ip(self, ip: str):
        s = self.settings
        self.limiter.reserve([self.limiter.rule("admin_ip", ip, s.admin_ip_limit, 60)])

    def refresh_ip(self, ip):
        policy = self.session_settings
        self.limiter.reserve([self.limiter.rule("refresh_ip", ip, policy.refresh_ip_limit, 60)])

    def refresh_session(self, sid):
        policy = self.session_settings
        self.limiter.reserve([self.limiter.rule("refresh_session", sid, policy.refresh_limit, 60)])

    @property
    def session_settings(self):
        return self.session_policy

    def login_reserve(self, email: str, ip: str):
        s = self.settings
        return self.limiter.reserve([self.limiter.rule("login_pair", email + "\0" + ip, s.login_limit, s.login_window)])

    def financial(self, request: Request, user_id: int, force=False):
        s = self.settings
        path = request.scope["path"]
        root = request.scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        path = path.rstrip("/")
        # Bucket keys use the category and verified user, never path/record IDs.
        if not force and path.startswith("/auth/") and path != "/auth/me" and not path.startswith("/auth/sessions"):
            return
        if path == "/admin/auth/step-up":
            return
        if path.startswith("/admin/"):
            self.limiter.reserve([self.limiter.rule("admin", str(user_id), s.admin_limit, s.financial_window)])
            return
        write = request.method in {"POST", "PUT", "PATCH", "DELETE"} and path != "/affordability"
        group, limit = ("writes", s.write_limit) if write else ("reads", s.read_limit)
        rules = [self.limiter.rule(group, str(user_id), limit, s.financial_window)]
        if path == "/forecast":
            rules.append(self.limiter.rule("forecast", str(user_id), s.forecast_limit, s.financial_window))
        elif path == "/affordability":
            rules.append(self.limiter.rule("affordability", str(user_id), s.affordability_limit, s.financial_window))
        self.limiter.reserve(rules)


def source_ip(scope) -> str:
    # Uvicorn may replace scope.client ONLY through explicitly trusted proxies.
    # Never parse arbitrary client-supplied forwarding headers in application code.
    host = (scope.get("client") or ("unknown", 0))[0]
    try:
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return str(address)
    except ValueError:
        return "unknown"  # All unidentified clients share a conservative bucket.
