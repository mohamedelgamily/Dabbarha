"""Atomic, bounded sliding windows. Production uses one shared private Redis."""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import hmac
import math
import threading
import time
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from redis.exceptions import RedisError

from app.core.private_redis import PrivateDNSSSLConnection


class StoreUnavailable(Exception):
    """Never includes backend connection strings or driver details."""


@dataclass(frozen=True)
class Rule:
    key: str
    limit: int
    window: int


class RateLimited(HTTPException):
    def __init__(self, retry: float):
        super().__init__(429, "Too many requests. Please try again later.",
                         headers={"Retry-After": str(max(1, math.ceil(retry)))})


def unavailable() -> HTTPException:
    return HTTPException(503, "Request protection is temporarily unavailable. Please try again shortly.",
                         headers={"Retry-After": "1"})


# All buckets are checked before any are charged. Redis TIME avoids worker clock skew.
# Members and keys are opaque; the script never receives email/password/token values.
ADMIT_SCRIPT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local retry = 0
for i,key in ipairs(KEYS) do
  local window = tonumber(ARGV[2*i]) * 1000
  local limit = tonumber(ARGV[2*i+1])
  redis.call('ZREMRANGEBYSCORE', key, '-inf', now-window)
  if redis.call('ZCARD', key) >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    retry = math.max(retry, tonumber(oldest[2]) + window - now)
  end
end
if retry > 0 then return retry end
for i,key in ipairs(KEYS) do
  local window = tonumber(ARGV[2*i]) * 1000
  redis.call('ZADD', key, now, ARGV[1])
  redis.call('PEXPIRE', key, window)
end
return 0
"""
RELEASE_SCRIPT = "for _,key in ipairs(KEYS) do redis.call('ZREM', key, ARGV[1]) end return 1"


class RedisStore:
    def __init__(self, url: str, timeout: float, allowed_cidrs: tuple[str, ...] = ()):
        options = {
            "socket_connect_timeout": timeout,
            "socket_timeout": timeout,
            "retry": Retry(NoBackoff(), 0),
            "max_connections": 32,
            "protocol": 2,
        }
        parsed = urlsplit(url)
        if parsed.scheme == "rediss":
            # Do not permit redis-py URL options to weaken TLS; URL query options
            # are rejected by configuration validation, and secure defaults are
            # explicit at this client boundary as well.
            options.update(ssl_cert_reqs="required", ssl_check_hostname=True)
        if allowed_cidrs:
            options.update(
                connection_class=PrivateDNSSSLConnection,
                allowed_cidrs=allowed_cidrs,
                dns_timeout=min(timeout, 2.0),
            )
        self.client = Redis.from_url(url, **options)
        self.admit_script = self.client.register_script(ADMIT_SCRIPT)
        self.release_script = self.client.register_script(RELEASE_SCRIPT)

    def ping(self):
        try:
            self.client.ping()
        except (RedisError, OSError, ValueError):
            raise StoreUnavailable() from None

    def admit(self, rules, token):
        args = [token]
        for rule in rules:
            args.extend([rule.window, rule.limit])
        try:
            retry = self.admit_script(keys=[r.key for r in rules], args=args)
        except (RedisError, OSError, ValueError):
            raise StoreUnavailable() from None
        if retry:
            raise RateLimited(int(retry) / 1000)

    def release(self, rules, token):
        try:
            self.release_script(keys=[r.key for r in rules], args=[token])
        except (RedisError, OSError, ValueError):
            raise StoreUnavailable() from None

    def close(self):
        self.client.close()


class MemoryStore:
    """Bounded and thread-safe; intentionally cannot be selected in production."""
    def __init__(self, clock=time.monotonic, max_keys=10000):
        self.clock, self.max_keys = clock, max_keys
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def ping(self):
        pass

    def admit(self, rules, token):
        with self.lock:
            now = self.clock()
            for key, (expires, _) in list(self.entries.items()):
                if expires <= now:
                    del self.entries[key]
            retry = 0
            for rule in rules:
                expires, entries = self.entries.get(rule.key, (0, {}))
                entries = {t: at for t, at in entries.items() if at > now-rule.window}
                if len(entries) >= rule.limit:
                    retry = max(retry, min(entries.values()) + rule.window-now)
                if rule.key in self.entries:
                    self.entries[rule.key] = (expires, entries)
            if retry > 0:
                raise RateLimited(retry)
            if len(self.entries) + sum(r.key not in self.entries for r in rules) > self.max_keys:
                raise StoreUnavailable()
            for rule in rules:
                _, entries = self.entries.get(rule.key, (0, {}))
                entries[token] = now
                self.entries[rule.key] = (now+rule.window, entries)

    def release(self, rules, token):
        with self.lock:
            for rule in rules:
                if rule.key in self.entries:
                    self.entries[rule.key][1].pop(token, None)

    def close(self):
        pass


class Limiter:
    def __init__(self, store, key: bytes):
        self.store, self.key = store, key

    def rule(self, group, identity, limit, window):
        digest = hmac.new(self.key, (group + "\0" + identity).encode(), hashlib.sha256).hexdigest()
        return Rule("dabbarha:rl:v1:" + group + ":" + digest, limit, window)

    def reserve(self, rules):
        token = uuid.uuid4().hex
        try:
            self.store.admit(rules, token)
        except StoreUnavailable:
            raise unavailable() from None
        return rules, token

    def release(self, reservation):
        try:
            self.store.release(*reservation)
        except StoreUnavailable:
            raise unavailable() from None
