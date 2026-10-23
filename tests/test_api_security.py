"""Abuse controls, wire compatibility and actual shared Redis concurrency regressions."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import logging
import multiprocessing
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
from unittest.mock import Mock

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from redis import Redis
from sqlalchemy import text
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.api_security import SecurityRuntime, source_ip
from app.core.api_security_settings import APISecuritySettings
from app.core.private_redis import PrivateDNSSSLConnection, resolve_allowed_private_addresses
from app.core.rate_limit import Limiter, MemoryStore, RateLimited, RedisStore, Rule, StoreUnavailable
from app.core.request_security import json_too_deep
from app.core.settings import ConfigurationError
from app.main import app
from tests.test_validation_integrity import api, PAYLOAD

KEY = b"Synthetic-ONLY-limiter-key-0123456789-abcdef"


@pytest.fixture(scope="session")
def redis_service():
    binary = os.environ.get("REDIS_SERVER_BINARY") or shutil.which("redis-server")
    if not binary:
        if os.environ.get("REQUIRE_REDIS_TESTS") == "1":
            pytest.fail("Redis integration tests are required but REDIS_SERVER_BINARY is missing.")
        pytest.skip("Set REDIS_SERVER_BINARY to run the required shared-Redis integration job.")
    # A newly spawned server with TCP disabled. Never connect to a user's database.
    with tempfile.TemporaryDirectory(prefix="dabbarha-rl-", dir="/tmp") as directory:
        socket = str(Path(directory) / "redis.sock")
        proc = subprocess.Popen([binary, "--port", "0", "--unixsocket", socket,
                                 "--unixsocketperm", "700", "--save", "", "--appendonly", "no",
                                 "--maxmemory", "32mb", "--maxmemory-policy", "noeviction",
                                 "--dir", directory, "--logfile", str(Path(directory)/"redis.log")],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = Redis(unix_socket_path=socket, socket_timeout=.5)
        try:
            deadline = time.monotonic()+10
            while True:
                try:
                    client.ping()
                    break
                except Exception:
                    if time.monotonic() > deadline or proc.poll() is not None:
                        pytest.fail("Disposable Redis did not start (driver output suppressed).")
                    time.sleep(.02)
            yield "unix://" + socket
        finally:
            client.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=5)


@pytest.fixture
def real_store(redis_service):
    store = RedisStore(redis_service, .5)
    store.client.flushdb()  # Exclusively the disposable server created above.
    yield store
    store.close()


def runtime(monkeypatch, **changes):
    value = SecurityRuntime(replace(APISecuritySettings(hmac_key=KEY), **changes))
    monkeypatch.setattr(app.state, "security", value)
    return value


def response_code(limiter, rules):
    try:
        limiter.reserve(rules)
        return 200
    except RateLimited:
        return 429


@pytest.mark.parametrize("implementation", ["memory", "redis"])
def test_atomic_concurrent_admission_and_independent_identities(implementation, request):
    store = request.getfixturevalue("real_store") if implementation == "redis" else MemoryStore()
    limiter = Limiter(store, KEY)
    rules = [limiter.rule("reads", "user-one", 5, 60)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(lambda _: response_code(limiter, rules), range(40)))
    assert codes.count(200) == 5 and codes.count(429) == 35
    assert response_code(limiter, [limiter.rule("reads", "user-two",5,60)]) == 200
    assert "user-one" not in rules[0].key


def test_expiry_retry_after_and_atomic_multibucket_check():
    now = [0.0]
    store = MemoryStore(clock=lambda: now[0])
    limiter = Limiter(store, KEY)
    general, expensive = Rule("general", 3, 10), Rule("expensive", 1, 10)
    limiter.reserve([general, expensive])
    now[0] = 1.1
    with pytest.raises(RateLimited) as exc:
        limiter.reserve([general, expensive])
    assert exc.value.headers["Retry-After"] == "9"
    assert len(store.entries["general"][1]) == 1  # No partial charge on rejection.
    now[0] = 10
    assert limiter.reserve([general, expensive])


def test_real_redis_expiry_and_reservation_release(real_store):
    limiter = Limiter(real_store, KEY)
    rule = limiter.rule("login_pair", "synthetic@example.com\x00127.0.0.1", 1, 1)
    reservation = limiter.reserve([rule])
    with pytest.raises(RateLimited): limiter.reserve([rule])
    limiter.release(reservation)
    limiter.reserve([rule])
    assert 0 < real_store.client.pttl(rule.key) <= 1000
    assert b"synthetic@example.com" not in b" ".join(real_store.client.keys("*"))
    time.sleep(1.05)
    limiter.reserve([rule])


def worker_admit(url, key, result, ready, start):
    store = RedisStore(url, 1)
    limiter = Limiter(store, key)
    rule = limiter.rule("reads", "same-user", 7, 60)
    ready.put(True)
    start.wait(10)
    result.put([response_code(limiter, [rule]) for _ in range(10)])
    store.close()


def test_independent_worker_processes_share_one_quota(real_store, redis_service):
    context = multiprocessing.get_context("spawn")
    result, ready, start = context.Queue(), context.Queue(), context.Event()
    workers = [context.Process(target=worker_admit, args=(redis_service,KEY,result,ready,start)) for _ in range(3)]
    try:
        for worker in workers: worker.start()
        for _ in workers: assert ready.get(timeout=15)
        start.set()
        codes = sum([result.get(timeout=15) for _ in workers], [])
        assert codes.count(200) == 7 and codes.count(429) == 23
    finally:
        for worker in workers:
            worker.join(timeout=10)
            if worker.is_alive(): worker.terminate(); worker.join(timeout=5)
        result.close(); ready.close()


def test_private_redis_configuration_and_startup_defaults():
    with pytest.raises(ConfigurationError): APISecuritySettings.from_environ("production", {})
    base = {"RATE_LIMIT_HMAC_KEY":KEY.decode(), "RATE_LIMIT_REDIS_URL":"redis://127.0.0.1:6379/0"}
    settings = APISecuritySettings.from_environ("production", base)
    assert settings.backend == "redis" and settings.login_limit == 5
    assert KEY.decode() not in repr(settings)
    for change in [
        {"RATE_LIMIT_BACKEND":"memory"}, {"RATE_LIMIT_HMAC_KEY":"placeholder"},
        {"JWT_SECRET_KEY":KEY.decode()}, {"RATE_LIMIT_REDIS_URL":"redis://8.8.8.8:6379"},
        {"RATE_LIMIT_REDIS_URL":"redis://0.0.0.0:6379"},
        {"RATE_LIMIT_REDIS_URL":"redis://redis.example.com:6379"},
        {"RATE_LIMIT_REDIS_URL":"redis://127.0.0.1/0?socket_timeout=999"},
        {"RATE_LIMIT_REDIS_URL":"redis://127.0.0.1:999999"},
        {"RATE_LIMIT_REDIS_URL":"https://127.0.0.1"},
        {"RATE_LIMIT_REDIS_URL":"unix://host/socket"},
    ]:
        with pytest.raises(ConfigurationError) as exc:
            APISecuritySettings.from_environ("production", base | change)
        assert KEY.decode() not in str(exc.value)
    assert APISecuritySettings.from_environ("development", {}).backend == "memory"
    assert APISecuritySettings.from_environ("production", base | {"RATE_LIMIT_REDIS_URL":"unix:///tmp/test.sock"}).backend == "redis"


def test_managed_redis_requires_tls_authentication_and_narrow_private_allowlist():
    dns_url = "rediss://limiter:synthetic-password@redis.internal.example:6380/0"
    env = {"RATE_LIMIT_HMAC_KEY": KEY.decode(), "RATE_LIMIT_REDIS_URL": dns_url,
           "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"}
    settings = APISecuritySettings.from_environ("production", env)
    assert settings.redis_allowed_cidrs == ("10.44.8.0/24",)
    store = RedisStore(settings.redis_url, .5, settings.redis_allowed_cidrs)
    try:
        connection = store.client.connection_pool.connection_class
        assert connection is PrivateDNSSSLConnection
        kwargs = store.client.connection_pool.connection_kwargs
        assert kwargs["ssl_cert_reqs"] == "required"
        assert kwargs["ssl_check_hostname"] is True
    finally:
        store.close()

    for changes in (
        {"RATE_LIMIT_REDIS_URL": "redis://limiter:synthetic-password@redis.internal.example:6379/0",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": "rediss://redis.internal.example:6380/0",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": dns_url, "RATE_LIMIT_REDIS_ALLOWED_CIDRS": ""},
        {"RATE_LIMIT_REDIS_URL": dns_url, "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "203.0.113.0/24"},
        {"RATE_LIMIT_REDIS_URL": dns_url, "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.0.0.0/8"},
        {"RATE_LIMIT_REDIS_URL": dns_url + "?ssl_cert_reqs=none",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": "rediss://limiter:synthetic-password@redis.internal.example:6380/0",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24,8.8.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": "rediss://limiter:@redis.internal.example:6380/0",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": "rediss://limiter:synthetic-password@redis:6380/0",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": "rediss://limiter:synthetic-password@-redis.internal.example:6380/0",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": "rediss://limiter:synthetic-password@redis.internal.example.:6380/0",
         "RATE_LIMIT_REDIS_ALLOWED_CIDRS": "10.44.8.0/24"},
        {"RATE_LIMIT_REDIS_URL": "redis://192.0.0.9:6379/0"},
        {"RATE_LIMIT_REDIS_URL": "redis://100.64.0.1:6379/0"},
    ):
        with pytest.raises(ConfigurationError):
            APISecuritySettings.from_environ("production", env | changes)

    with pytest.raises(ValueError):
        PrivateDNSSSLConnection(
            host="redis.internal.example", port=6380, password="synthetic-password",
            ssl_cert_reqs="none", ssl_check_hostname=False,
            allowed_cidrs=("10.44.8.0/24",), dns_timeout=.5,
        )


def test_private_dns_answers_are_checked_on_every_connection(monkeypatch):
    import app.core.private_redis as private_redis

    answers = [["10.44.8.12", ""], ["203.0.113.12", ""]]
    calls = [0]

    class Resolver:
        def __init__(self, configure=True):
            pass

        def resolve(self, host, record_type, *, lifetime, search):
            assert host == "redis.internal.example" and lifetime > 0 and search is False
            values = answers[calls[0]][0 if record_type == "A" else 1]
            if record_type == "AAAA":
                calls[0] += 1
            return [type("Record", (), {"address": value}) for value in ([values] if values else [])]

    monkeypatch.setattr(private_redis.dns.resolver, "Resolver", Resolver)
    cidrs = ("10.44.8.0/24",)
    assert str(resolve_allowed_private_addresses("redis.internal.example", cidrs, .5)[0]) == "10.44.8.12"
    with pytest.raises(OSError):
        resolve_allowed_private_addresses("redis.internal.example", cidrs, .5)
    assert calls[0] == 2


def test_managed_redis_public_dns_answer_fails_closed_without_network(monkeypatch):
    import app.core.private_redis as private_redis

    class Resolver:
        def __init__(self, configure=True):
            pass

        def resolve(self, host, record_type, *, lifetime, search):
            return [type("Record", (), {"address": "8.8.8.8" if record_type == "A" else ""})] if record_type == "A" else []

    monkeypatch.setattr(private_redis.dns.resolver, "Resolver", Resolver)
    store = RedisStore("rediss://limiter:synthetic-password@redis.internal.example:6380/0", .5,
                       ("10.44.8.0/24",))
    try:
        with pytest.raises(StoreUnavailable):
            store.ping()
    finally:
        store.close()


@pytest.mark.parametrize("name,value", [("RATE_LIMIT_READS","0"),("RATE_LIMIT_WRITES","-1"),("RATE_LIMIT_LOGIN","no"),
    ("RATE_LIMIT_REGISTRATION","100001"),("API_BODY_TIMEOUT_SECONDS","nan"),
    ("RATE_LIMIT_REDIS_TIMEOUT_SECONDS","inf"),("AUTH_ARGON2_WAIT_SECONDS","0"),
    ("API_MAX_JSON_DEPTH","10000"),("API_MAX_BODY_BYTES","0"),("AUTH_ARGON2_CONCURRENCY","33")])
def test_invalid_settings_fail_safely(name, value):
    with pytest.raises(ConfigurationError) as exc:
        APISecuritySettings.from_environ("test", {name:value})
    assert name in str(exc.value)


def test_thresholds_are_configurable():
    settings = APISecuritySettings.from_environ("test", {
        "RATE_LIMIT_LOGIN":"2","RATE_LIMIT_LOGIN_IP":"8","RATE_LIMIT_LOGIN_WINDOW_SECONDS":"20",
        "RATE_LIMIT_REGISTRATION":"3","RATE_LIMIT_REGISTRATION_WINDOW_SECONDS":"40",
        "RATE_LIMIT_WRITES":"4","RATE_LIMIT_READS":"9","RATE_LIMIT_FORECAST":"6",
        "RATE_LIMIT_AFFORDABILITY":"7","RATE_LIMIT_FINANCIAL_WINDOW_SECONDS":"30",
        "API_MAX_BODY_BYTES":"2048","API_MAX_JSON_DEPTH":"8","API_BODY_TIMEOUT_SECONDS":"2",
        "AUTH_ARGON2_CONCURRENCY":"1","AUTH_ARGON2_WAIT_SECONDS":"0.1"})
    assert (settings.login_limit,settings.login_ip_limit,settings.login_window)==(2,8,20)
    assert (settings.registration_limit,settings.registration_window)==(3,40)
    assert (settings.write_limit,settings.read_limit,settings.forecast_limit,settings.affordability_limit)==(4,9,6,7)
    assert settings.financial_window==30 and settings.body_bytes==2048 and settings.json_depth==8
    assert settings.body_timeout==2 and settings.argon_wait==.1


def test_login_pair_inflight_and_success_release_does_not_reset_other_failures(monkeypatch):
    value = runtime(monkeypatch, login_limit=2)
    failure = value.login_reserve("known@example.com", "127.0.0.1")
    success = value.login_reserve("known@example.com", "127.0.0.1")
    with pytest.raises(RateLimited): value.login_reserve("known@example.com", "127.0.0.1")
    value.limiter.release(success)
    value.login_reserve("known@example.com", "127.0.0.1")
    with pytest.raises(RateLimited): value.login_reserve("known@example.com", "127.0.0.1")
    assert value.login_reserve("known@example.com", "192.168.1.2")
    assert value.login_reserve("other@example.com", "127.0.0.1")


def test_login_unknown_and_known_accounts_have_same_failure_contract(api, monkeypatch):
    from app.api.routes import auth
    client, _, _, _ = api
    runtime(monkeypatch, login_limit=2)
    verifier = Mock(return_value=False)
    monkeypatch.setattr(auth,"verify_password",verifier)
    responses=[]
    for email in ["owner@example.com", "unknown@example.com"]:
        responses.append([client.post("/auth/login",json={"email":email,"password":"bad"}) for _ in range(3)])
    assert verifier.call_count == 4  # Unknown accounts also incur equivalent work.
    for left, right in zip(*responses):
        assert left.status_code == right.status_code
        assert left.json() == right.json()
    assert [r.status_code for r in responses[0]] == [401,401,429]
    assert responses[0][-1].headers["Retry-After"] == "900"


def test_successful_login_removes_its_reservation_and_keeps_token_contract(api, monkeypatch):
    from app.api.routes import auth
    client, session, _, _ = api
    runtime(monkeypatch, login_limit=1)
    monkeypatch.setattr(auth,"verify_password",Mock(return_value=True))
    for _ in range(3):
        response=client.post("/auth/login",json={"email":"owner@example.com","password":"ok"})
        assert response.status_code==200 and set(response.json())=={"access_token","token_type"}
        assert response.headers["Cache-Control"] == "no-store"
    assert session.scalar(text("SELECT count(*) FROM users"))==2


def test_ip_guard_and_forged_headers_cannot_change_source(api, monkeypatch):
    client, _, _, _ = api
    runtime(monkeypatch, login_ip_limit=2)
    for index in range(3):
        response=client.post("/auth/login",json={"email":f"unknown{index}@example.com","password":"bad"},
                             headers={"X-Forwarded-For":f"10.0.0.{index}","Forwarded":f"for=10.0.0.{index}","X-Real-IP":f"10.0.0.{index}"})
        assert response.status_code==(401 if index<2 else 429)
    assert source_ip({"client":("::ffff:192.168.1.1",1)})=="192.168.1.1"


def test_admin_totp_step_up_uses_shared_account_ip_attempt_limits(api, monkeypatch):
    client, _, _, _ = api
    runtime(monkeypatch, login_ip_limit=2)
    for index in range(3):
        response = client.post("/admin/auth/step-up", json={"code": "000000"},
                               headers={"X-Forwarded-For": f"10.0.0.{index}"})
        assert response.status_code == (404 if index < 2 else 429)


def test_registration_guard_counts_invalid_and_duplicate_requests(api, monkeypatch):
    client, _, _, _ = api
    runtime(monkeypatch, registration_limit=2)
    assert client.post("/auth/register",json={}).status_code==422
    assert client.post("/auth/register",json={"name":"Owner","email":"owner@example.com","password":"unchanged"}).status_code==409
    assert client.post("/auth/register/",json={}).status_code==429


def test_read_quotas_shared_across_routes_and_users_are_independent(api, monkeypatch):
    from app.core.security import create_access_token
    client, _, headers, ids = api
    runtime(monkeypatch, read_limit=2)
    assert client.get("/auth/me",headers=headers).status_code==200
    assert client.get("/dashboard/summary",headers=headers).status_code==200
    denied=client.get("/obligations",headers=headers)
    assert denied.status_code==429 and int(denied.headers["Retry-After"])>0
    other={"Authorization":"Bearer "+create_access_token(subject=str(ids[1]))}
    assert client.get("/obligations",headers=other).status_code==200
    assert client.get("/obligations",headers={"Authorization":"Bearer forged","X-User-ID":str(ids[1])}).status_code==401


def test_write_quota_covers_profile_and_obligation_crud(api, monkeypatch):
    client, _, headers, _ = api
    runtime(monkeypatch, write_limit=3)
    assert client.patch("/auth/me",headers=headers,json={"monthly_income":"0"}).status_code==200
    created=client.post("/obligations",headers=headers,json=PAYLOAD)
    assert created.status_code==201
    url=f"/obligations/{created.json()['id']}"
    assert client.put(url,headers=headers,json={"provider":"تمويل"}).status_code==200
    assert client.delete(url,headers=headers).status_code==429
    assert client.get(url,headers=headers).status_code==200


@pytest.mark.parametrize("path,limit",[("/forecast","forecast_limit"),("/affordability","affordability_limit")])
def test_expensive_evaluations_have_additional_quotas(api, monkeypatch, path, limit):
    client, _, headers, _ = api
    runtime(monkeypatch, **{limit:1})
    def call():
        if path=="/forecast":return client.get(path,headers=headers,params={"start_month":"2026-01-01","months":1})
        return client.post(path,headers=headers,json={"amount":"0","start_date":"2026-01-01","term_months":1})
    assert call().status_code==200
    assert call().status_code==429
    assert client.get("/dashboard/summary",headers=headers).status_code==200


def test_fail_closed_on_backend_error_and_safe_startup(api, monkeypatch, caplog):
    client, _, headers, _ = api
    value=runtime(monkeypatch)
    def failed(*args):raise StoreUnavailable()
    monkeypatch.setattr(value.limiter.store,"admit",failed)
    for path in ["/auth/me","/obligations","/dashboard/summary"]:
        response=client.get(path,headers=headers)
        assert response.status_code==503 and response.headers["Retry-After"]=="1"
        assert response.headers["Cache-Control"]=="no-store"
    assert client.post("/auth/login",json={"email":"unknown@example.com","password":"secret"}).status_code==503
    assert client.get("/health").status_code==200
    monkeypatch.setattr(value.limiter.store,"ping",failed)
    with pytest.raises(RuntimeError,match="startup refused"):
        with TestClient(app):pass
    assert "secret" not in caplog.text


def test_redis_transport_errors_are_redacted(monkeypatch):
    from redis.exceptions import ConnectionError
    store=RedisStore("redis://127.0.0.1:1",.01)
    def failed(*args,**kwargs):raise ConnectionError("PRIVATE PASSWORD redis://user:private@host SQL")
    monkeypatch.setattr(store,"admit_script",failed)
    with pytest.raises(HTTPException) as exc:
        Limiter(store,KEY).reserve([Rule("test",1,60)])
    assert exc.value.status_code==503 and "PRIVATE" not in str(exc.value.detail)
    monkeypatch.setattr(store.client,"ping",failed)
    with pytest.raises(StoreUnavailable) as exc:store.ping()
    assert str(exc.value)==""
    store.close()


def test_password_wait_is_bounded_and_released(monkeypatch):
    value=runtime(monkeypatch,argon_concurrency=1,argon_wait=.02)
    with value.password_slot():
        start=time.monotonic()
        with pytest.raises(HTTPException) as exc:
            with value.password_slot():pass
        assert exc.value.status_code==503 and time.monotonic()-start<.5
    with value.password_slot():pass


@pytest.mark.parametrize("path,method,expected",[("/health","GET",200),("/auth/me","GET",401),("/auth/login","GET",405),("/chat","POST",404)])
def test_security_headers_and_cors_remain_closed(api,path,method,expected):
    client,_,_,_=api
    response=client.request(method,path,headers={"Origin":"https://untrusted.example"})
    assert response.status_code==expected
    assert response.headers["Cache-Control"]=="no-store"
    assert response.headers["X-Content-Type-Options"]=="nosniff"
    assert response.headers["Referrer-Policy"]=="no-referrer"
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Credentials" not in response.headers
    assert "Strict-Transport-Security" not in response.headers
    if expected==405:assert "POST" in response.headers["Allow"]
    preflight=client.options("/auth/login",headers={"Origin":"https://untrusted.example","Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"authorization,content-type"})
    assert "Access-Control-Allow-Origin" not in preflight.headers


def test_oversize_json_unicode_and_safe_errors(api, monkeypatch, caplog):
    client, _, headers, _=api
    value=runtime(monkeypatch,body_bytes=512)
    response=client.post("/auth/login",content=b"x"*513,headers={"Content-Type":"application/json"})
    assert response.status_code==413 and response.headers["Cache-Control"]=="no-store"
    assert client.post("/obligations",headers=headers,json=PAYLOAD).status_code==201
    assert client.post("/auth/login",content="{"*65,headers={"Content-Type":"application/json"}).status_code==422
    assert client.post("/auth/login",content=b"{garbage",headers={"Content-Type":"application/json"}).status_code==422
    assert client.post("/auth/login",content=b"compressed",headers={"Content-Encoding":"gzip"}).status_code==415
    def failed(*args):raise RuntimeError("PRIVATE password=hidden SQL")
    monkeypatch.setattr(value,"auth_ip",failed)
    with caplog.at_level(logging.ERROR):
        result=client.post("/auth/login",json={"email":"unknown@example.com","password":"hidden"})
    assert result.status_code==500 and "PRIVATE" not in result.text
    assert "hidden" not in caplog.text and "PRIVATE" not in caplog.text
    assert "api_request_failed" in caplog.text


def test_depth_scanner_preserves_escaped_unicode_strings():
    assert not json_too_deep(json.dumps({"text":"عربي English \\\" [[[[{{{{"}).encode(),1)
    assert not json_too_deep(b"["*64+b"0"+b"]"*64,64)
    assert json_too_deep(b"["*65+b"0"+b"]"*65,64)


async def raw_request(messages, *, headers=(), timeout=.02):
    from app.core.request_security import RequestSecurityMiddleware
    called=[]; sent=[]
    async def inner(scope,receive,send):
        called.append(await receive())
        await send({"type":"http.response.start","status":200,"headers":[]})
        await send({"type":"http.response.body","body":b"ok"})
    wrapper=RequestSecurityMiddleware(inner)
    value=SecurityRuntime(replace(APISecuritySettings(),body_bytes=16,body_timeout=timeout))
    scope={"type":"http","app":type("App",(),{"state":type("State",(),{"security":value})()})(),
           "headers":headers,"path":"/health","method":"GET","client":("192.168.1.1",1)}
    events=iter(messages)
    async def receive():
        item=next(events,None)
        if item is None:
            await asyncio.sleep(1)
            return {"type":"http.disconnect"}
        return item
    async def send(message):sent.append(message)
    await wrapper(scope,receive,send)
    return sent[0]["status"],called


def test_streamed_body_limits_missing_or_false_length_and_timeout():
    event=lambda body,more=False:{"type":"http.request","body":body,"more_body":more}
    for headers in [[],[(b"content-length",b"1")]]:
        status,called=asyncio.run(raw_request([event(b"x"*8,True),event(b"y"*9)],headers=headers))
        assert status==413 and not called
    status,called=asyncio.run(raw_request([event(b"x"*8,True),event(b"y"*8)]))
    assert status==200 and called[0]["body"]==b"x"*8+b"y"*8
    status,called=asyncio.run(raw_request([event(b"x",True)]))
    assert status==408 and not called
    for lengths in [[(b"content-length",b"-1")],[(b"content-length",b"x")],[(b"content-length",b"1"),(b"content-length",b"2")]]:
        assert asyncio.run(raw_request([event(b"x")],headers=lengths))[0]==400
    assert asyncio.run(raw_request([event(b"xx")],headers=[(b"content-length",b"1")]))[0]==400


def test_uvicorn_trust_boundary_ignores_untrusted_forwarding():
    async def scenario(peer):
        captured=[]
        async def inner(scope,receive,send):captured.append(source_ip(scope))
        wrapped=ProxyHeadersMiddleware(inner,trusted_hosts=["127.0.0.1"])
        await wrapped({"type":"http","client":(peer,1),"scheme":"http", "headers":[(b"x-forwarded-for",b"192.168.2.3")]},None,None)
        return captured[0]
    assert asyncio.run(scenario("192.168.1.4"))=="192.168.1.4"
    assert asyncio.run(scenario("127.0.0.1"))=="192.168.2.3"


def test_bounded_development_store_fails_safely_when_full():
    limiter=Limiter(MemoryStore(max_keys=1),KEY)
    limiter.reserve([Rule("one",1,60)])
    with pytest.raises(HTTPException) as exc:limiter.reserve([Rule("two",1,60)])
    assert exc.value.status_code==503


def test_actual_redis_runtime_startup_api_quota_and_private_socket(api, monkeypatch, real_store, redis_service):
    client, _, headers, _ = api
    settings=APISecuritySettings.from_environ("production", {
        "RATE_LIMIT_REDIS_URL":redis_service,"RATE_LIMIT_HMAC_KEY":KEY.decode(),
        "RATE_LIMIT_READS":"1"})
    monkeypatch.setattr(app.state,"security",SecurityRuntime(settings))
    assert real_store.client.config_get("port")["port"]=="0"
    with TestClient(app) as second_worker:
        assert second_worker.get("/auth/me",headers=headers).status_code==200
        assert client.get("/dashboard/summary",headers=headers).status_code==429


def test_actual_missing_redis_service_refuses_startup_and_requests(api, monkeypatch, tmp_path):
    client, _, headers, _=api
    settings=APISecuritySettings.from_environ("production",{
        "RATE_LIMIT_REDIS_URL":"unix:///tmp/dabbarha-never-created-test.sock",
        "RATE_LIMIT_HMAC_KEY":KEY.decode(),"RATE_LIMIT_REDIS_TIMEOUT_SECONDS":"0.02"})
    monkeypatch.setattr(app.state,"security",SecurityRuntime(settings))
    with pytest.raises(RuntimeError,match="startup refused"):
        with TestClient(app):pass
    response=client.get("/auth/me",headers=headers)
    assert response.status_code==503 and "sock" not in response.text


@pytest.mark.parametrize("subject",[str(2**63),"9"*100,"0","-1"])
def test_extreme_signed_subjects_are_401_without_database_errors(api,subject):
    from app.core.security import create_access_token
    client,_,_,_=api
    response=client.get("/auth/me",headers={"Authorization":"Bearer "+create_access_token(subject=subject)})
    assert response.status_code==401 and response.headers["WWW-Authenticate"]=="Bearer"


def test_http_quota_expires_and_ip_pair_does_not_globally_lock_account(api,monkeypatch):
    from app.api.routes import auth
    client,_,_,_=api
    value=runtime(monkeypatch,login_limit=1,login_window=10)
    now=[0.0]
    value.limiter.store=MemoryStore(clock=lambda:now[0])
    monkeypatch.setattr(auth,"verify_password",Mock(return_value=False))
    body={"email":"owner@example.com","password":"bad"}
    assert client.post("/auth/login",json=body).status_code==401
    assert client.post("/auth/login",json=body).status_code==429
    with TestClient(app,client=("192.168.1.2",2000)) as alternate_ip:
        assert alternate_ip.post("/auth/login",json=body).status_code==401
    now[0]=10
    assert client.post("/auth/login",json=body).status_code==401


def test_argon_failure_releases_pending_login_reservation(api,monkeypatch):
    from app.api.routes import auth
    client,_,_,_=api
    value=runtime(monkeypatch,login_limit=1,argon_concurrency=1,argon_wait=.01)
    body={"email":"owner@example.com","password":"bad"}
    with value.password_slot():
        response=client.post("/auth/login",json=body)
    assert response.status_code==503 and response.headers["Retry-After"]=="1"
    monkeypatch.setattr(auth,"verify_password",Mock(return_value=False))
    assert client.post("/auth/login",json=body).status_code==401


def test_security_settings_support_ipv6_loopback_and_redis_url_errors_are_safe():
    base={"RATE_LIMIT_HMAC_KEY":KEY.decode()}
    assert APISecuritySettings.from_environ("production",base|{"RATE_LIMIT_REDIS_URL":"redis://[::1]:6379/0"}).backend=="redis"
    with pytest.raises(ConfigurationError) as exc:
        APISecuritySettings.from_environ("production",base|{"RATE_LIMIT_REDIS_URL":"redis://user:PRIVATE@8.8.8.8:6379"})
    assert "PRIVATE" not in str(exc.value)


def test_absurd_declared_body_length_is_safe_413():
    status,called=asyncio.run(raw_request([],headers=[(b"content-length",b"9"*5000)]))
    assert status==413 and not called


def test_production_application_import_requires_shared_limiter_configuration():
    import sys
    key=secrets.token_urlsafe(48)
    environment={k:v for k,v in os.environ.items() if k in {"PATH","TMPDIR","SYSTEMROOT"}}
    environment.update(APP_ENV="production",JWT_SECRET_KEY=key,DATABASE_URL="sqlite:///:memory:",PYTHONDONTWRITEBYTECODE="1")
    result=subprocess.run([sys.executable,"-c","import app.main"],env=environment,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert result.returncode!=0 and "RATE_LIMIT_HMAC_KEY" in result.stderr
    assert key not in result.stderr+result.stdout


def test_two_argon_slots_bound_concurrent_work_and_waiting():
    import threading
    from queue import Queue
    value=SecurityRuntime(replace(APISecuritySettings(),argon_concurrency=2,argon_wait=.01))
    ready=Queue(); release=threading.Event()
    def hold():
        with value.password_slot():
            ready.put(True)
            assert release.wait(5)
    def attempt():
        try:
            with value.password_slot():return 200
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=10) as pool:
        holders=[pool.submit(hold) for _ in range(2)]
        try:
            assert ready.get(timeout=5) and ready.get(timeout=5)
            assert list(pool.map(lambda _:attempt(),range(12)))==[503]*12
        finally:
            release.set()
        for holder in holders:holder.result(timeout=5)
        assert attempt()==200


@pytest.mark.parametrize("user_id", [-1, 0])
def test_existing_representable_user_ids_keep_authentication_compatibility(api, user_id):
    from app.models.user import User
    from app.core.security import create_access_token
    client, session, _, _ = api
    session.add(User(id=user_id, name="Legacy ID", email=f"legacy{user_id}@example.com", password_hash="unused"))
    session.commit()
    response=client.get("/auth/me",headers={"Authorization":"Bearer "+create_access_token(subject=str(user_id))})
    assert response.status_code==200 and response.json()["id"]==user_id
