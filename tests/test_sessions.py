"""Device-session protocol regressions against isolated, disposable databases."""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Event
from uuid import uuid4
import secrets
import time

from fastapi import HTTPException
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import event as sqlalchemy_event, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.core.notification_settings import NotificationSettings
from app.core.session_settings import SessionSettings
from app.core.settings import ConfigurationError
from app.db.database import Base, create_app_engine
from app.main import app
from app.models.auth_session import AuthRefreshToken, AuthSession, LegacyAccessRevocation
from app.models.notifications import (
    Notification, NotificationDelivery, NotificationPreference, PaymentOccurrence,
    PaymentOccurrenceEvent, PushDevice,
)
from app.models.obligation import Obligation, ObligationInstallment
from app.models.user import User
from app.services.notification_worker import _send_one, run_once
from app.services.notifications import encrypt_push_token
from app.services.sessions import SessionService, digest
from app.services.push_provider import SendResult
from tests.postgres_test_support import initialize_disposable_postgres


@pytest.fixture(scope="session")
def postgres_service():
    binary_dir = os.environ.get("POSTGRES_TEST_BIN")
    if not binary_dir:
        if os.environ.get("REQUIRE_POSTGRES_TESTS") == "1":
            pytest.fail("POSTGRES_TEST_BIN must name disposable PostgreSQL runtime binaries.")
        pytest.skip("Set POSTGRES_TEST_BIN for disposable PostgreSQL integration tests.")
    import psycopg
    with tempfile.TemporaryDirectory(prefix="dabbarha-pg-", dir="/tmp") as directory:
        root = Path(directory)
        initialize_disposable_postgres(binary_dir, root / "data", root)
        with (root/"server.log").open("w") as log:
            proc = subprocess.Popen([str(Path(binary_dir)/"postgres"), "-D", str(root/"data"),
                "-k", directory, "-h", "", "-c", "unix_socket_permissions=0700"], stdout=log, stderr=log)
            try:
                deadline = time.monotonic()+15
                while True:
                    try:
                        with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test"):
                            break
                    except psycopg.Error:
                        if proc.poll() is not None or time.monotonic() > deadline:
                            pytest.fail("Disposable PostgreSQL did not start (output suppressed).")
                        time.sleep(.05)
                yield directory
            finally:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)


@pytest.fixture(params=["sqlite", "postgres"])
def session_db(tmp_path, request):
    if request.param == "sqlite":
        engine = create_app_engine(f"sqlite:///{tmp_path / 'sessions.db'}")
    else:
        import psycopg
        from psycopg import sql
        directory = request.getfixturevalue("postgres_service")
        name = "test_" + uuid4().hex
        with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test", autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        from sqlalchemy.engine import URL
        engine = create_app_engine(URL.create("postgresql+psycopg", username="dabbarha_test", database=name,
                                             query={"host":directory}).render_as_string(hide_password=False))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    if request.param == "postgres":
        with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test", autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def service():
    return SessionService(SessionSettings(enabled=True, receipt_key=secrets.token_bytes(32)))


@pytest.fixture
def user_id(session_db):
    with Session(session_db) as db:
        user = User(name="Session User", email="session@example.com", password_hash=hash_password("password"))
        db.add(user); db.commit()
        return user.id


@pytest.fixture
def session_api(session_db, service, user_id, monkeypatch):
    monkeypatch.setattr(app.state, "sessions", service)
    def override():
        with Session(session_db) as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            yield client, service, session_db, user_id
    finally:
        app.dependency_overrides.clear()


def bearer(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def code(call):
    try:
        return 200, call()
    except HTTPException as exc:
        return exc.status_code, exc.detail


@pytest.mark.parametrize("length,expected", [(0,422),(7,422),(8,201),(128,201),(129,422)])
def test_registration_boundaries(session_api, length, expected):
    client, *_ = session_api
    r = client.post("/auth/register", json={"name":"New", "email":"new@example.com", "password":"ع"*length})
    assert r.status_code == expected
    assert "password_hash" not in r.text


@pytest.mark.parametrize("password", ["        ", "\ud800abcdefgh"])
def test_invalid_registration_password(session_api, password):
    client, *_ = session_api
    body = json.dumps({"name":"New", "email":"new@example.com", "password":password})
    r = client.post("/auth/register", content=body, headers={"Content-Type":"application/json"})
    assert r.status_code == 422
    assert password not in r.text


def test_unicode_password_unchanged(session_api):
    client, _, engine, _ = session_api
    password = "  كلمة سر عربية e\u0301  "
    assert client.post("/auth/register", json={"name":"اسم", "email":"unicode@example.com", "password":password}).status_code == 201
    assert client.post("/auth/login", json={"email":"unicode@example.com", "password":password}).status_code == 200
    with Session(engine) as db:
        row = db.scalar(select(User).where(User.email == "unicode@example.com"))
        assert row.password_hash.startswith("$argon2id$")
        assert verify_password(password, row.password_hash)
        assert not verify_password(password.strip(), row.password_hash)


def test_legacy_login_and_optional_profile_preserved(session_api):
    client, _, engine, uid = session_api
    with Session(engine) as db:
        user = db.get(User, uid); user.password_hash = hash_password("x"); db.commit()
        old_hash = user.password_hash
    r = client.post("/auth/login", json={"email":"session@example.com", "password":"x"})
    assert r.status_code == 200 and set(r.json()) == {"access_token","token_type"}
    from app.core.security import decode_access_token
    payload = decode_access_token(r.json()["access_token"])
    assert set(payload) == {"sub","exp"} and 3590 <= payload["exp"]-time.time() <= 3600
    assert client.get("/auth/me", headers=bearer(r.json())).json()["monthly_income"] == "0.00"
    with Session(engine) as db:
        assert db.get(User, uid).password_hash == old_hash


def test_new_login_refresh_and_no_plaintext_storage(session_api):
    client, service, engine, uid = session_api
    r = client.post("/auth/sessions", json={"email":"session@example.com","password":"password","device_label":"هاتف"})
    assert r.status_code == 200
    original = r.json(); key = secrets.token_urlsafe(32)
    assert original["expires_in"] == 900 and r.headers["cache-control"] == "no-store"
    response = client.post("/auth/refresh", json={"refresh_token":original["refresh_token"],"retry_key":key})
    assert response.status_code == 200
    pair = response.json()
    with Session(engine) as db:
        row = db.get(AuthRefreshToken, digest(original["refresh_token"]))
        data = repr({c.name:getattr(row,c.name) for c in row.__table__.columns})
        for secret in [key, original["refresh_token"], pair["refresh_token"], pair["access_token"]]:
            assert secret not in data
        assert row.response_ciphertext and row.retry_key_hash == digest(key)
    assert client.get("/auth/me", headers=bearer(pair)).status_code == 200
    assert client.get("/auth/me", headers={"Authorization":"Bearer "+pair["refresh_token"]}).status_code == 401
    assert client.get("/auth/sessions", headers=bearer(pair)).json()[0]["current"] is True


def test_lost_response_restart_and_exact_retry_limit(session_db, service, user_id):
    pair = service.create(session_db,user_id,None); key = secrets.token_urlsafe(32)
    rotated = service.refresh(session_db,pair["refresh_token"],key) # Pretend response never reached the phone.
    restarted = SessionService(service.settings)
    for _ in range(2):
        assert restarted.refresh(session_db,pair["refresh_token"],key) == rotated
    assert code(lambda: restarted.refresh(session_db,pair["refresh_token"],key))[0] == 409
    with Session(session_db) as db:
        row = db.get(AuthRefreshToken,digest(pair["refresh_token"]))
        assert row.recovery_count == 2 and row.response_ciphertext is None
        assert db.get(AuthSession,pair["session_id"]).revoked_at is None


def test_parallel_same_operation_is_atomic(session_db,service,user_id):
    pair=service.create(session_db,user_id,None); key=secrets.token_urlsafe(32)
    def run(_):
        return code(lambda: SessionService(service.settings).refresh(session_db,pair["refresh_token"],key))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(run,range(8)))
    assert [x[0] for x in results].count(200)==3
    assert [x[0] for x in results].count(409)==5
    winners=[x[1] for x in results if x[0]==200]
    assert all(pair == winners[0] for pair in winners)
    with Session(session_db) as db:
        assert db.get(AuthSession,pair["session_id"]).current_generation==1


def test_different_keys_conflict_then_revoke_only_affected_family(session_db,service,user_id):
    now=[int(time.time())]; service.clock=lambda:now[0]
    pair=service.create(session_db,user_id,None); other=service.create(session_db,user_id,None)
    key=secrets.token_urlsafe(32); service.refresh(session_db,pair["refresh_token"],key)
    assert code(lambda:service.refresh(session_db,pair["refresh_token"],secrets.token_urlsafe(32)))==(409,"refresh_conflict")
    now[0]+=60
    assert code(lambda:service.refresh(session_db,pair["refresh_token"],secrets.token_urlsafe(32)))[0]==401
    with Session(session_db) as db:
        assert db.get(AuthSession,pair["session_id"]).revocation_reason=="refresh_reuse"
        assert db.get(AuthSession,other["session_id"]).revoked_at is None
        assert db.get(AuthRefreshToken,digest(pair["refresh_token"])).response_ciphertext is None


@pytest.mark.parametrize("elapsed,expected", [(59,200),(60,409),(61,409)])
def test_exact_receipt_deadline(session_db,service,user_id,elapsed,expected):
    now=[int(time.time())];service.clock=lambda:now[0]
    pair=service.create(session_db,user_id,None);key=secrets.token_urlsafe(32)
    original=service.refresh(session_db,pair["refresh_token"],key);now[0]+=elapsed
    status,result=code(lambda:service.refresh(session_db,pair["refresh_token"],key))
    assert status==expected
    if status==200: assert result==original


def test_successor_consumption_blocks_old_recovery(session_db,service,user_id):
    first=service.create(session_db,user_id,None);key=secrets.token_urlsafe(32)
    second=service.refresh(session_db,first["refresh_token"],key)
    service.refresh(session_db,second["refresh_token"],secrets.token_urlsafe(32))
    assert code(lambda:service.refresh(session_db,first["refresh_token"],key))[0]==409
    with Session(session_db) as db:
        assert db.get(AuthRefreshToken,digest(first["refresh_token"])).response_ciphertext is None


@pytest.mark.parametrize("failure",["ciphertext","nonce","key","key_id"])
def test_encryption_failure_safe_no_quota_consumption(session_db,service,user_id,failure):
    first=service.create(session_db,user_id,None);key=secrets.token_urlsafe(32)
    service.refresh(session_db,first["refresh_token"],key)
    if failure=="key":service.settings=replace(service.settings,receipt_key=secrets.token_bytes(32))
    else:
        with Session(session_db) as db:
            row=db.get(AuthRefreshToken,digest(first["refresh_token"]))
            if failure=="ciphertext":row.response_ciphertext=b"tampered"
            elif failure=="nonce":row.encryption_nonce=b"invalid"
            else:row.encryption_key_id="wrong"
            db.commit()
    assert code(lambda:service.refresh(session_db,first["refresh_token"],key))[0]==503
    with Session(session_db) as db:
        assert db.get(AuthRefreshToken,digest(first["refresh_token"])).recovery_count==0


def test_encrypt_failure_rolls_back_rotation(session_db,service,user_id,monkeypatch):
    first=service.create(session_db,user_id,None)
    from app.services import sessions
    class Broken:
        def __init__(self,*args):pass
        def encrypt(self,*args):raise RuntimeError("synthetic sensitive failure")
    monkeypatch.setattr(sessions,"ReceiptCipher",Broken)
    assert code(lambda:service.refresh(session_db,first["refresh_token"],secrets.token_urlsafe(32)))[0]==503
    with Session(session_db) as db:
        assert db.get(AuthRefreshToken,digest(first["refresh_token"])).consumed_at is None
        assert db.get(AuthSession,first["session_id"]).current_generation==0


def test_logout_revokes_access_and_refresh_idempotently(session_api):
    client,service,engine,uid=session_api
    first=service.create(engine,uid,None);other=service.create(engine,uid,None)
    for _ in range(2):assert client.post("/auth/logout",headers=bearer(first)).status_code==204
    assert client.get("/auth/me",headers=bearer(first)).status_code==401
    assert client.get("/auth/me",headers=bearer(other)).status_code==200
    assert client.post("/auth/refresh",json={"refresh_token":first["refresh_token"],"retry_key":secrets.token_urlsafe(32)}).status_code==401
    for _ in range(2):assert client.post("/auth/logout",json={"refresh_token":other["refresh_token"]}).status_code==204
    assert client.post("/auth/logout",json={"refresh_token":secrets.token_urlsafe(32)}).status_code==204


def test_legacy_logout_fingerprint_survives_request_rollback(session_api):
    client,_,engine,uid=session_api
    token=create_access_token(str(uid));headers={"Authorization":"Bearer "+token}
    assert client.post("/auth/logout",headers=headers).status_code==204
    assert client.post("/auth/logout",headers=headers).status_code==204
    assert client.get("/auth/me",headers=headers).status_code==401
    with Session(engine) as db:assert len(db.scalars(select(LegacyAccessRevocation)).all())==1


def test_password_confirmed_revocation_and_cross_user_ownership(session_api):
    client,service,engine,uid=session_api
    first=service.create(engine,uid,None);second=service.create(engine,uid,None)
    with Session(engine) as db:
        user=User(name="Other",email="other@example.com",password_hash=hash_password("password"));db.add(user);db.commit();other_id=user.id
    other=service.create(engine,other_id,None)
    path=f"/auth/sessions/{second['session_id']}/revoke"
    assert client.post(path,headers=bearer(first),json={"password":"wrong"}).status_code==401
    assert client.post(path,headers=bearer(first),json={"password":"password"}).status_code==204
    assert client.get("/auth/me",headers=bearer(second)).status_code==401
    assert client.post(f"/auth/sessions/{other['session_id']}/revoke",headers=bearer(first),json={"password":"password"}).status_code==404
    ids=[row["id"] for row in client.get("/auth/sessions",headers=bearer(first)).json()]
    assert other["session_id"] not in ids


def test_cleanup_retains_consumed_hash_until_absolute_expiration(session_db,service,user_id):
    now=[int(time.time())];service.clock=lambda:now[0]
    first=service.create(session_db,user_id,None);service.refresh(session_db,first["refresh_token"],secrets.token_urlsafe(32))
    now[0]+=60;service.cleanup(session_db)
    with Session(session_db) as db:
        row=db.get(AuthRefreshToken,digest(first["refresh_token"]))
        assert row and row.response_ciphertext is None and row.retry_key_hash
    now[0]=first["session_expires_at"];service.cleanup(session_db)
    with Session(session_db) as db:
        assert db.get(AuthSession,first["session_id"]) is None
        assert db.get(AuthRefreshToken,digest(first["refresh_token"])) is None


@pytest.mark.parametrize("settings",[{}, {"SESSION_AUTH_ENABLED":"true"},
    {"SESSION_AUTH_ENABLED":"true","SESSION_RECEIPT_KEY":base64.b64encode(b"x"*32).decode()},
    {"SESSION_AUTH_ENABLED":"true","SESSION_RECEIPT_KEY":"<placeholder>"}])
def test_receipt_key_configuration(settings):
    if not settings:assert not SessionSettings.from_environ(settings).enabled
    else:
        with pytest.raises(ConfigurationError):SessionSettings.from_environ(settings)


def test_missing_credentials_cannot_recover(session_api):
    client,service,engine,uid=session_api
    pair=service.create(engine,uid,None)
    assert client.post("/auth/refresh",json={"retry_key":secrets.token_urlsafe(32)}).status_code==422
    assert client.post("/auth/refresh",json={"refresh_token":pair["refresh_token"]}).status_code==422
    assert client.post("/auth/refresh",json={"refresh_token":"NaN","retry_key":"invalid"}).status_code==422
    assert client.post("/auth/refresh",json={"refresh_token":secrets.token_urlsafe(32),"retry_key":secrets.token_urlsafe(32)}).status_code==401
    assert client.post("/auth/logout").status_code==422
    assert client.post("/auth/logout",headers=bearer(pair),json={"refresh_token":pair["refresh_token"]}).status_code==422


@pytest.mark.parametrize("mutation", [{"ver":3},{"ver":True},{"sid":"wrong"},{"jti":"wrong"},
    {"token_use":"refresh"},{"iat":True},{"sid":None}])
def test_malformed_new_claims_never_fall_back(session_api,mutation):
    from app.core.config import JWT_SECRET_KEY
    from app.core.security import decode_access_token
    client,service,engine,uid=session_api
    pair=service.create(engine,uid,None)
    payload=decode_access_token(pair["access_token"])|mutation
    token=jwt.encode(payload,JWT_SECRET_KEY,algorithm="HS256")
    assert client.get("/auth/me",headers={"Authorization":"Bearer "+token}).status_code==401


def test_expiration_and_absolute_cap(session_db,service,user_id):
    now=[int(time.time())];service.clock=lambda:now[0]
    first=service.create(session_db,user_id,None)
    now[0]=first["refresh_expires_at"]
    assert code(lambda:service.refresh(session_db,first["refresh_token"],secrets.token_urlsafe(32)))[0]==401
    now[0]=first["session_expires_at"]-10
    # Simulate a currently active family close to its hard deadline.
    with Session(session_db) as db:
        db.get(AuthSession,first["session_id"]).idle_expires_at=first["session_expires_at"]
        db.get(AuthRefreshToken,digest(first["refresh_token"])).expires_at=first["session_expires_at"]
        db.commit()
    last=service.refresh(session_db,first["refresh_token"],secrets.token_urlsafe(32))
    assert last["expires_in"]==10 and last["refresh_expires_at"]==first["session_expires_at"]


def test_old_refresh_expired_after_rotation_still_recovers(session_db,service,user_id):
    now=[int(time.time())];service.clock=lambda:now[0]
    first=service.create(session_db,user_id,None);key=secrets.token_urlsafe(32)
    now[0]=first["refresh_expires_at"]-1
    second=service.refresh(session_db,first["refresh_token"],key)
    now[0]+=2
    assert service.refresh(session_db,first["refresh_token"],key)==second


def test_commit_failure_and_lost_commit_ack(session_db,service,user_id,monkeypatch):
    first=service.create(session_db,user_id,None);key=secrets.token_urlsafe(32)
    original=Session.commit
    def failed(_db):raise RuntimeError("synthetic DB failure")
    monkeypatch.setattr(Session,"commit",failed)
    assert code(lambda:service.refresh(session_db,first["refresh_token"],key))[0]==503
    monkeypatch.setattr(Session,"commit",original)
    with Session(session_db) as db:
        assert db.get(AuthRefreshToken,digest(first["refresh_token"])).consumed_at is None
    def lost_ack(db):original(db);raise RuntimeError("synthetic lost acknowledgement")
    monkeypatch.setattr(Session,"commit",lost_ack)
    assert code(lambda:service.refresh(session_db,first["refresh_token"],key))[0]==503
    monkeypatch.setattr(Session,"commit",original)
    recovered=service.refresh(session_db,first["refresh_token"],key)
    assert recovered["session_id"]==first["session_id"]
    with Session(session_db) as db:assert db.get(AuthSession,first["session_id"]).current_generation==1


def test_refresh_logout_race_cannot_resurrect(session_db,service,user_id):
    first=service.create(session_db,user_id,None);key=secrets.token_urlsafe(32)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(lambda:code(lambda:service.refresh(session_db,first["refresh_token"],key)))
        b=pool.submit(lambda:service.logout_refresh(session_db,first["refresh_token"]))
        assert a.result()[0] in {200,401};b.result()
    assert code(lambda:service.refresh(session_db,first["refresh_token"],key))[0]==401
    with Session(session_db) as db:
        assert db.get(AuthSession,first["session_id"]).revoked_at is not None
        assert all(row.response_ciphertext is None for row in db.scalars(select(AuthRefreshToken)).all())


def test_refresh_quotas_and_forwarded_header_forgery(session_api,monkeypatch):
    client,service,engine,uid=session_api
    runtime=app.state.security
    runtime.session_policy=replace(runtime.session_policy,refresh_ip_limit=3,refresh_limit=2)
    pair=service.create(engine,uid,None);key=secrets.token_urlsafe(32)
    body={"refresh_token":pair["refresh_token"],"retry_key":key}
    assert client.post("/auth/refresh",json=body).status_code==200
    assert client.post("/auth/refresh",json=body).status_code==200
    r=client.post("/auth/refresh",json=body,headers={"X-Forwarded-For":"1.2.3.4"})
    assert r.status_code==429 and int(r.headers["Retry-After"])>0
    other=service.create(engine,uid,None)
    assert client.post("/auth/refresh",json={"refresh_token":other["refresh_token"],"retry_key":key},
                       headers={"X-Forwarded-For":"5.6.7.8"}).status_code==429


def test_new_login_uses_legacy_ip_bucket(session_api):
    client,*_=session_api
    for _ in range(30):
        assert client.post("/auth/login",json={}).status_code==422
    r=client.post("/auth/sessions",json={"email":"session@example.com","password":"password"})
    assert r.status_code==429


def test_disabled_feature_preserves_legacy_and_refuses_new_routes(session_api):
    client,service,engine,uid=session_api
    service.settings=replace(service.settings,enabled=False)
    assert client.post("/auth/login",json={"email":"session@example.com","password":"password"}).status_code==200
    assert client.get("/auth/me",headers={"Authorization":"Bearer "+create_access_token(str(uid))}).status_code==200
    assert client.post("/auth/sessions",json={"email":"session@example.com","password":"password"}).status_code==503


def test_additive_migration_and_downgrade_only_disposable_db(session_db):
    # session_db is created exclusively by this fixture; never an environment URL.
    from alembic.config import Config
    from alembic import command
    from unittest.mock import patch
    from sqlalchemy import inspect
    import app.core.config as config
    Base.metadata.drop_all(session_db)
    cfg=Config("alembic.ini")
    url=session_db.url.render_as_string(hide_password=False)
    with patch.object(config,"DATABASE_URL",url):
        command.upgrade(cfg,"2d1a00000001")
        assert {"auth_sessions","auth_refresh_tokens","legacy_access_revocations"} <= set(inspect(session_db).get_table_names())
        assert {"notification_preferences", "notification_devices", "payment_occurrences",
                "payment_occurrence_events", "notifications", "notification_deliveries"} <= set(inspect(session_db).get_table_names())
        assert "obligation_installments" in inspect(session_db).get_table_names()
        assert {
            "purchase_price", "payment_method", "interest_method", "nominal_annual_interest_rate",
            "down_payment_amount", "down_payment_date", "down_payment_paid", "schedule_version",
        } <= {column["name"] for column in inspect(session_db).get_columns("obligations")}
        with Session(session_db) as db:
            db.execute(text("INSERT INTO users (name, email, password_hash, monthly_income, fixed_expenses, currency) "
                            "VALUES ('Before deletion migration', 'pre-migration@example.com', 'existing-hash', 0, 0, 'EGP')"))
            db.commit()
            preexisting_id = db.scalar(text("SELECT id FROM users WHERE email='pre-migration@example.com'"))
        command.upgrade(cfg,"head")
        assert "account_id_sequence" in inspect(session_db).get_table_names()
        assert "admin_audit_events" in inspect(session_db).get_table_names()
        assert "worker_heartbeats" in inspect(session_db).get_table_names()
        assert {"admin_role", "admin_totp_nonce", "admin_totp_ciphertext", "admin_totp_key_id", "admin_totp_last_step"} <= {
            column["name"] for column in inspect(session_db).get_columns("users")}
        from app.models.account_id_sequence import AccountIdSequence
        with Session(session_db) as db:
            assert db.get(AccountIdSequence, 1).last_id == preexisting_id
            assert db.get(User, preexisting_id).admin_role == "user"
        with Session(session_db) as db:
            db.execute(text("INSERT INTO users (name, email, password_hash, monthly_income, fixed_expenses, currency) "
                            "VALUES ('Preserved', 'preserved@example.com', 'existing-hash', 0, 0, 'EGP')"))
            db.commit()
        command.downgrade(cfg,"17d4d0e39961")
        assert "auth_sessions" not in inspect(session_db).get_table_names()
        assert not ({"notification_preferences", "notification_devices", "payment_occurrences",
                     "payment_occurrence_events", "notifications", "notification_deliveries"}
                    & set(inspect(session_db).get_table_names()))
        assert "account_id_sequence" not in inspect(session_db).get_table_names()
        assert "admin_audit_events" not in inspect(session_db).get_table_names()
        assert "worker_heartbeats" not in inspect(session_db).get_table_names()
        assert "admin_role" not in {column["name"] for column in inspect(session_db).get_columns("users")}
        assert "obligation_installments" not in inspect(session_db).get_table_names()
        assert "purchase_price" not in {column["name"] for column in inspect(session_db).get_columns("obligations")}
        with Session(session_db) as db:assert db.scalar(text("SELECT password_hash FROM users"))=="existing-hash"
        command.upgrade(cfg,"head")
        assert "admin_audit_events" in inspect(session_db).get_table_names()
        assert "worker_heartbeats" in inspect(session_db).get_table_names()


def test_admin_totp_step_up_is_session_bound_audited_and_replay_safe(session_api, monkeypatch):
    import time
    from app.core.admin_settings import AdminSettings
    from app.models.admin_audit import AdminAuditEvent
    from app.services.admin_security import encrypt_totp_secret, generate_totp_secret, totp_code
    client, service, engine, uid = session_api
    key = secrets.token_bytes(32)
    policy = AdminSettings(enabled=True, totp_encryption_key=key)
    monkeypatch.setattr(app.state, "admin_settings", policy)
    secret = generate_totp_secret()
    nonce, ciphertext = encrypt_totp_secret(secret, uid, policy)
    with Session(engine) as db:
        user = db.get(User, uid)
        user.admin_role = "admin"
        user.admin_totp_nonce, user.admin_totp_ciphertext = nonce, ciphertext
        user.admin_totp_key_id = policy.totp_key_id
        db.commit()
    pair = service.create(engine, uid, "test-device")
    now = int(time.time())
    code = totp_code(secret, now // 30)
    headers = bearer(pair)
    response = client.post("/admin/auth/step-up", json={"code": code}, headers=headers)
    assert response.status_code == 200
    admin_token = response.json()["access_token"]
    admin_headers = {"Authorization": "Bearer " + admin_token}
    assert client.get("/admin/auth/me", headers=admin_headers).status_code == 200
    assert client.post("/admin/auth/step-up", json={"code": code}, headers=headers).status_code == 401
    with Session(engine) as db:
        events = db.scalars(select(AdminAuditEvent).order_by(AdminAuditEvent.id)).all()
        assert [event.outcome for event in events] == ["success", "success", "failure"]
        assert all(not hasattr(event, "code") and not hasattr(event, "token") for event in events)
        user = db.get(User, uid)
        user.admin_role = "user"  # A live role downgrade invalidates the still-unexpired step-up token.
        db.commit()
    assert client.get("/admin/auth/me", headers=admin_headers).status_code == 403


def test_admin_rejects_legacy_access_tokens(session_api, monkeypatch):
    from app.core.admin_settings import AdminSettings
    client, _, _, uid = session_api
    monkeypatch.setattr(app.state, "admin_settings", AdminSettings(enabled=True,
        totp_encryption_key=secrets.token_bytes(32)))
    legacy = create_access_token(str(uid))
    response = client.post("/admin/auth/step-up", json={"code": "000000"}, headers=bearer({"access_token": legacy}))
    assert response.status_code == 401


def test_admin_endpoints_are_hidden_when_feature_is_off(session_api, monkeypatch):
    from app.core.admin_settings import AdminSettings
    client, service, engine, uid = session_api
    monkeypatch.setattr(app.state, "admin_settings", AdminSettings(enabled=False))
    response = client.post("/admin/auth/step-up", json={"code": "000000"})
    assert response.status_code == 404


def test_admin_totp_concurrent_replay_only_one_step_up(session_api, monkeypatch):
    import time
    from app.core.admin_settings import AdminSettings
    from app.services.admin_security import encrypt_totp_secret, generate_totp_secret, totp_code
    client, service, engine, uid = session_api
    policy = AdminSettings(enabled=True, totp_encryption_key=secrets.token_bytes(32))
    monkeypatch.setattr(app.state, "admin_settings", policy)
    secret = generate_totp_secret()
    nonce, ciphertext = encrypt_totp_secret(secret, uid, policy)
    with Session(engine) as db:
        user = db.get(User, uid)
        user.admin_role = "superadmin"
        user.admin_totp_nonce, user.admin_totp_ciphertext = nonce, ciphertext
        user.admin_totp_key_id = policy.totp_key_id
        db.commit()
    pair = service.create(engine, uid, "parallel-test")
    headers = bearer(pair)
    code = totp_code(secret, int(time.time()) // 30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/admin/auth/step-up", json={"code": code}, headers=headers).status_code,
                                range(2)))
    assert sorted(results) == [200, 401]


def _worker_refresh(arguments):
    # Independent process, engine, session and service; no shared in-memory lock.
    url, settings, token, key = arguments
    engine=create_app_engine(url)
    try:return code(lambda:SessionService(settings).refresh(engine,token,key))
    finally:engine.dispose()


def test_independent_workers_share_atomic_recovery_budget(session_db,service,user_id):
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    first=service.create(session_db,user_id,None);key=secrets.token_urlsafe(32)
    args=(session_db.url.render_as_string(hide_password=False),service.settings,first["refresh_token"],key)
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context("spawn")) as pool:
        results=list(pool.map(_worker_refresh,[args]*6))
    assert sorted(status for status,_ in results)==[200,200,200,409,409,409]
    successes=[pair for status,pair in results if status==200]
    assert all(pair==successes[0] for pair in successes)


def test_missing_session_tables_return_safe_503(session_api):
    client,service,engine,uid=session_api
    AuthRefreshToken.__table__.drop(engine)
    r=client.post("/auth/refresh",json={"refresh_token":secrets.token_urlsafe(32),"retry_key":secrets.token_urlsafe(32)})
    assert r.status_code==503 and "SELECT" not in r.text and "auth_refresh_tokens" not in r.text


def test_new_auth_routes_fail_closed_with_actual_redis_outage(session_api,request,monkeypatch):
    from tests.test_api_security import redis_service
    from app.core.rate_limit import RedisStore
    directory=request.getfixturevalue("redis_service")
    client,service,engine,uid=session_api
    pair=service.create(engine,uid,None)
    runtime=app.state.security
    store=RedisStore(directory,.5)
    monkeypatch.setattr(runtime.limiter,"store",store)
    try:
        assert client.post("/auth/refresh",json={"refresh_token":pair["refresh_token"],"retry_key":secrets.token_urlsafe(32)}).status_code==200
        # Use a missing socket on that disposable server's private directory.
        broken=RedisStore(directory+"-missing",.1)
        monkeypatch.setattr(runtime.limiter,"store",broken)
        try:
            assert client.post("/auth/refresh",json={"refresh_token":pair["refresh_token"],"retry_key":secrets.token_urlsafe(32)}).status_code==503
            assert client.post("/auth/logout",json={"refresh_token":pair["refresh_token"]}).status_code==503
        finally:broken.close()
    finally:store.close()


# Make the existing actual-disposable-Redis fixture available to this module.
from tests.test_api_security import redis_service


def test_aead_known_answer_and_authenticated_metadata():
    # NIST GCM AES-256, zero key/96-bit IV, empty plaintext and AAD.
    from app.core.receipts import ReceiptCipher
    cipher=ReceiptCipher(bytes(32));nonce=bytes(12)
    assert cipher.encrypt(nonce,b"",b"").hex()=="530f8afbc74536b9a963b4f1c4cb738b"
    encrypted=cipher.encrypt(nonce,b"synthetic receipt",b"session-one")
    assert cipher.decrypt(nonce,encrypted,b"session-one")==b"synthetic receipt"
    with pytest.raises(ValueError):cipher.decrypt(nonce,encrypted,b"session-two")


def test_valid_session_configuration_and_key_separation():
    key=base64.b64encode(secrets.token_bytes(32)).decode()
    env={"SESSION_AUTH_ENABLED":"true","SESSION_RECEIPT_KEY":key}
    assert len(SessionSettings.from_environ(env).receipt_key)==32
    for other in ("JWT_SECRET_KEY","RATE_LIMIT_HMAC_KEY"):
        with pytest.raises(ConfigurationError):SessionSettings.from_environ(env|{other:key})
    for name,value in [("SESSION_REFRESH_IDLE_DAYS","91"),("SESSION_ABSOLUTE_DAYS","0"),
                       ("SESSION_REFRESH_LIMIT","NaN"),("SESSION_RECEIPT_KEY_ID","../bad")]:
        with pytest.raises(ConfigurationError):SessionSettings.from_environ(env|{name:value})


@pytest.mark.parametrize("expiry",[float("inf"),float("nan"),[],{}])
def test_malformed_signed_numeric_claims_are_401(session_api,expiry):
    from app.core.config import JWT_SECRET_KEY
    client,_,_,uid=session_api
    token=jwt.encode({"sub":str(uid),"exp":expiry},JWT_SECRET_KEY,algorithm="HS256")
    assert client.get("/auth/me",headers={"Authorization":"Bearer "+token}).status_code==401


def test_financial_contracts_and_ownership_with_session_jwts(session_api):
    from tests.test_validation_integrity import PAYLOAD
    client,service,engine,uid=session_api
    pair=service.create(engine,uid,"Owner phone");headers=bearer(pair)
    legacy={"Authorization":"Bearer "+create_access_token(str(uid))}
    assert client.patch("/auth/me",headers=headers,json={"monthly_income":"1000","fixed_expenses":"100"}).status_code==200
    created=client.post("/obligations",headers=headers,json=PAYLOAD)
    assert created.status_code==201
    oid=created.json()["id"]
    assert client.put(f"/obligations/{oid}",headers=headers,json={"provider":"Updated"}).status_code==200
    reads=["/obligations",f"/obligations/{oid}","/dashboard/summary","/forecast?start_month=2026-01-01&months=2"]
    for path in reads:
        current=client.get(path,headers=headers);old=client.get(path,headers=legacy)
        assert current.status_code==old.status_code==200
        assert current.json()==old.json()
    body={"amount":"10","start_date":"2026-01-01","term_months":2}
    assert client.post("/affordability",headers=headers,json=body).json()==client.post("/affordability",headers=legacy,json=body).json()
    with Session(engine) as db:
        other=User(name="Other",email="financial-other@example.com",password_hash="unused")
        db.add(other);db.commit();other_id=other.id
    other_pair=service.create(engine,other_id,None)
    assert client.get("/obligations",headers=bearer(other_pair)).json()==[]
    assert client.get(f"/obligations/{oid}",headers=bearer(other_pair)).status_code==404
    assert client.post("/auth/logout",headers=headers).status_code==204
    for path in reads:assert client.get(path,headers=headers).status_code==401
    assert client.post("/affordability",headers=headers,json=body).status_code==401
    # Logout is per family: independent historical legacy credentials are unaffected.
    assert client.get("/auth/me",headers=legacy).status_code==200
    assert client.delete(f"/obligations/{oid}",headers=legacy).status_code==204


def _deletion_auth(client, access_token, password="password"):
    return client.request("DELETE", "/auth/account", headers={"Authorization": f"Bearer {access_token}"},
                          json={"password": password, "confirm_permanent_deletion": True})


def _create_legacy_conversation_tables(engine):
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE conversations (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL "
            "REFERENCES users(id) ON DELETE CASCADE)"
        ))
        connection.execute(text(
            "CREATE TABLE conversation_messages (id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL "
            "REFERENCES conversations(id) ON DELETE CASCADE, content TEXT NOT NULL)"
        ))


def _seed_account_private_data(engine, service, user_id):
    now = datetime.now(timezone.utc)
    pair = service.create(engine, user_id, "delete-test-device")
    token_settings = NotificationSettings(enabled=True, token_key=secrets.token_bytes(32))
    with Session(engine) as db:
        user = db.get(User, user_id)
        user.monthly_income = Decimal("1234.56")
        user.fixed_expenses = Decimal("321.00")
        obligation = Obligation(
            user_id=user_id, provider="Private provider", item_name="Private plan", category="other",
            total_amount=Decimal("100.00"), monthly_installment_amount=Decimal("10.00"),
            start_date=date.today(), term_months=10, due_day_of_month=5,
            status="active", source="manual_entry",
        )
        db.add(obligation)
        db.flush()
        installment = ObligationInstallment(
            obligation_id=obligation.id, installment_number=1, due_date=date.today(),
            scheduled_amount=Decimal("10.00"), principal_amount=Decimal("10.00"),
            interest_amount=Decimal("0.00"),
        )
        db.add(installment)
        db.flush()
        occurrence = PaymentOccurrence(
            user_id=user_id, obligation_id=obligation.id, installment_id=installment.id,
            occurrence_key="regular:deletion-test", payment_kind="regular", due_date=date.today(),
            scheduled_amount=Decimal("10.00"), schedule_version=0, state="paid", paid_at=now,
        )
        db.add(occurrence)
        db.flush()
        db.add_all([
            PaymentOccurrenceEvent(occurrence_id=occurrence.id, user_id=user_id, action="marked_paid"),
            LegacyAccessRevocation(fingerprint="d" * 64, user_id=user_id, revoked_at=int(now.timestamp()),
                                   expires_at=int(now.timestamp()) + 3600),
            NotificationPreference(user_id=user_id, reminders_enabled=True, categories=["payment_completed"]),
        ])
        auth_session = db.scalar(select(AuthSession).where(AuthSession.id == pair["session_id"]))
        push = "ExpoPushToken[DeletionTestToken12345678901234567890]"
        token_hash, token_ciphertext, token_nonce = encrypt_push_token(
            token_settings, push, user_id, auth_session.id)
        device = PushDevice(
            user_id=user_id, session_id=auth_session.id, token_hash=token_hash,
            token_ciphertext=token_ciphertext, token_nonce=token_nonce, token_key_id="v1",
            platform="ios", active=True,
        )
        db.add(device)
        db.flush()
        notification = Notification(
            user_id=user_id, obligation_id=obligation.id, occurrence_id=occurrence.id,
            notification_type="payment_completed", deduplication_key=f"delete-test:{user_id}",
            scheduled_at=now, title="Private notification", body="Private body",
            copy_version="v1", route="obligation_detail", delivery_state="queued",
        )
        db.add(notification)
        db.flush()
        db.add(NotificationDelivery(notification_id=notification.id, device_id=device.id,
                                    delivery_state="queued", attempt_count=0, receipt_attempt_count=0))
        db.commit()
    _create_legacy_conversation_tables(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO conversations (id, user_id) VALUES (1, :uid)"), {"uid": user_id})
        connection.execute(text("INSERT INTO conversation_messages (id, conversation_id, content) VALUES (1, 1, 'private old chat')"))
    return pair, token_settings


def test_account_deletion_cascades_all_private_rows_and_invalidates_old_tokens(session_api):
    client, service, engine, user_id = session_api
    pair, _ = _seed_account_private_data(engine, service, user_id)
    from app.models.admin_audit import AdminAuditEvent
    with Session(engine) as db:
        db.add(AdminAuditEvent(actor_user_id=user_id, target_user_id=user_id,
                               action="admin_totp_step_up", outcome="failure"))
        db.commit()
    legacy_token = create_access_token(str(user_id))
    headers = bearer(pair)
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {legacy_token}"}).status_code == 200

    response = _deletion_auth(client, pair["access_token"])
    assert response.status_code == 204, response.text
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {legacy_token}"}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": pair["refresh_token"],
                                               "retry_key": secrets.token_urlsafe(32)}).status_code == 401

    expected_empty = [
        User, Obligation, ObligationInstallment, AuthSession, AuthRefreshToken,
        LegacyAccessRevocation, NotificationPreference, PushDevice, PaymentOccurrence,
        PaymentOccurrenceEvent, Notification, NotificationDelivery,
    ]
    with Session(engine) as db:
        for model in expected_empty:
            assert db.scalar(select(model).limit(1)) is None, model.__tablename__
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM conversations")) == 0
        assert connection.scalar(text("SELECT COUNT(*) FROM conversation_messages")) == 0
        # Only a global, non-user-linked allocator remains.
        assert connection.scalar(text("SELECT COUNT(*) FROM account_id_sequence")) in {0, 1}
    with Session(engine) as db:
        audit_event = db.scalar(select(AdminAuditEvent))
        assert audit_event is not None
        assert audit_event.actor_user_id is None and audit_event.target_user_id is None

    # Repeating with a stale credential is harmless and cannot recreate data.
    assert _deletion_auth(client, pair["access_token"]).status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(User.id).where(User.id == user_id)) is None


def test_account_deletion_requires_correct_password_and_explicit_confirmation(session_api):
    client, service, engine, user_id = session_api
    pair = service.create(engine, user_id, "confirm-test")
    bad_password = _deletion_auth(client, pair["access_token"], "wrong-password")
    assert bad_password.status_code == 401
    no_confirmation = client.request("DELETE", "/auth/account", headers=bearer(pair),
                                     json={"password": "password", "confirm_permanent_deletion": False})
    assert no_confirmation.status_code == 422
    with Session(engine) as db:
        assert db.get(User, user_id) is not None


def test_account_id_is_not_reused_after_deletion(session_api):
    client, service, engine, user_id = session_api
    pair = service.create(engine, user_id, "id-reuse-test")
    response = _deletion_auth(client, pair["access_token"])
    assert response.status_code == 204
    registered = client.post("/auth/register", json={
        "name": "Replacement", "email": "replacement-account@example.com", "password": "password-123",
    })
    assert registered.status_code == 201, registered.text
    assert registered.json()["id"] != user_id
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"}).status_code == 401


def test_concurrent_sqlite_registrations_allocate_distinct_account_ids(session_api):
    client, _service, engine, _user_id = session_api
    bodies = [{"name": f"Concurrent {index}", "email": f"concurrent-{index}@example.com",
               "password": "password-123"} for index in range(5)]
    with ThreadPoolExecutor(max_workers=len(bodies)) as pool:
        responses = list(pool.map(lambda body: client.post("/auth/register", json=body), bodies))
    assert [response.status_code for response in responses] == [201] * len(bodies)
    ids = [response.json()["id"] for response in responses]
    assert len(ids) == len(set(ids))
    with Session(engine) as db:
        assert len(db.scalars(select(User.id).where(User.id.in_(ids))).all()) == len(bodies)


def test_public_account_deletion_information_is_bilingual_and_requires_no_login(session_api):
    client, *_ = session_api
    response = client.get("/privacy/account-deletion")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Delete your Dabbarha account" in response.text
    assert "حذف حساب دبّرها" in response.text
    assert "This information page does not itself receive or process requests" in response.text


def test_account_deletion_isolated_to_authenticated_user(session_api):
    client, service, engine, user_id = session_api
    pair = service.create(engine, user_id, "owner")
    with Session(engine) as db:
        other = User(name="Other account", email="other-deletion@example.com",
                     password_hash=hash_password("other-password"))
        db.add(other)
        db.commit()
        other_id = other.id
    other_pair = service.create(engine, other_id, "other")
    response = _deletion_auth(client, pair["access_token"])
    assert response.status_code == 204
    assert client.get("/auth/me", headers=bearer(other_pair)).status_code == 200
    with Session(engine) as db:
        assert db.get(User, user_id) is None
        assert db.get(User, other_id) is not None


def test_account_deletion_database_failure_rolls_back_everything(session_api):
    client, service, engine, user_id = session_api
    pair, _ = _seed_account_private_data(engine, service, user_id)

    def fail_user_delete(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "DELETE FROM USERS" in statement.upper():
            raise RuntimeError("injected disposable-test failure")

    sqlalchemy_event.listen(engine, "before_cursor_execute", fail_user_delete)
    try:
        response = _deletion_auth(client, pair["access_token"])
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", fail_user_delete)
    assert response.status_code == 503
    with Session(engine) as db:
        assert db.get(User, user_id) is not None
        assert db.scalar(select(Obligation).where(Obligation.user_id == user_id)) is not None
        assert db.scalar(select(AuthSession).where(AuthSession.user_id == user_id)) is not None
        assert db.scalar(select(PushDevice).where(PushDevice.user_id == user_id)) is not None
        assert db.scalar(select(PaymentOccurrence).where(PaymentOccurrence.user_id == user_id)) is not None
        assert db.scalar(select(Notification).where(Notification.user_id == user_id)) is not None
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM conversations WHERE user_id = :uid"), {"uid": user_id}) == 1
        assert connection.scalar(text("SELECT COUNT(*) FROM conversation_messages")) == 1


def test_concurrent_account_deletion_is_atomic_and_idempotent(session_api):
    client, service, engine, user_id = session_api
    pair = service.create(engine, user_id, "concurrent-delete")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _deletion_auth(client, pair["access_token"]), range(2)))
    codes = sorted(response.status_code for response in responses)
    assert codes[0] == 204
    assert codes[1] in {401, 503}
    with Session(engine) as db:
        assert db.get(User, user_id) is None
        assert db.scalar(select(AuthSession).where(AuthSession.user_id == user_id)) is None


def test_refresh_racing_account_deletion_cannot_leave_valid_session(session_api):
    client, service, engine, user_id = session_api
    pair = service.create(engine, user_id, "refresh-delete-race")
    entered, release = Event(), Event()

    def delayed_refresh():
        def hold(_session_id):
            entered.set()
            assert release.wait(timeout=5)
        try:
            return service.refresh(engine, pair["refresh_token"], secrets.token_urlsafe(32), hold)
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        refresh_future = pool.submit(delayed_refresh)
        assert entered.wait(timeout=3)
        delete_future = pool.submit(_deletion_auth, client, pair["access_token"])
        time.sleep(0.1)
        release.set()
        deletion_response = delete_future.result(timeout=10)
        refresh_result = refresh_future.result(timeout=10)
    assert deletion_response.status_code == 204
    if isinstance(refresh_result, dict):
        assert client.get("/auth/me", headers=bearer(refresh_result)).status_code == 401
    else:
        assert refresh_result == 401


def test_notification_worker_send_and_deletion_share_bounded_account_lock(session_api):
    client, service, engine, user_id = session_api
    pair = service.create(engine, user_id, "worker-delete-race")
    settings = NotificationSettings(enabled=True, delivery_enabled=True, token_key=secrets.token_bytes(32))
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(NotificationPreference(user_id=user_id, reminders_enabled=True,
                                      categories=["payment_completed"], reminder_offsets=[0]))
        obligation = Obligation(
            user_id=user_id, provider="Worker provider", item_name="Worker plan", category="other",
            total_amount=Decimal("10.00"), monthly_installment_amount=Decimal("10.00"),
            start_date=date.today(), term_months=1, due_day_of_month=1,
            status="active", source="manual_entry",
        )
        db.add(obligation); db.flush()
        occurrence = PaymentOccurrence(
            user_id=user_id, obligation_id=obligation.id, occurrence_key="worker-delete",
            payment_kind="regular", due_date=date.today(), scheduled_amount=Decimal("10.00"),
            state="paid", paid_at=now,
        )
        db.add(occurrence); db.flush()
        token_hash, ciphertext, nonce = encrypt_push_token(
            settings, "ExpoPushToken[WorkerDeleteRaceToken1234567890]", user_id, pair["session_id"])
        device = PushDevice(user_id=user_id, session_id=pair["session_id"], token_hash=token_hash,
                            token_ciphertext=ciphertext, token_nonce=nonce, token_key_id="v1",
                            platform="android", active=True)
        db.add(device); db.flush()
        notification = Notification(
            user_id=user_id, obligation_id=obligation.id, occurrence_id=occurrence.id,
            notification_type="payment_completed", deduplication_key=f"worker-delete:{user_id}",
            scheduled_at=now, title="Payment marked", body="You marked it paid",
            route="obligation_detail", delivery_state="sending",
        )
        db.add(notification); db.flush()
        delivery = NotificationDelivery(notification_id=notification.id, device_id=device.id,
                                         delivery_state="sending", attempt_count=1,
                                         lease_until=now + timedelta(seconds=30))
        db.add(delivery); db.commit(); delivery_id = delivery.id

    class BlockingProvider:
        def __init__(self):
            self.entered, self.release, self.sent = Event(), Event(), []
        def send(self, token, title, body, data):
            self.entered.set()
            assert self.release.wait(timeout=3)
            self.sent.append(token)
            return SendResult(True, ticket_id="bounded-test-ticket")

    provider = BlockingProvider()
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker_future = pool.submit(_send_one, engine, delivery_id, settings, provider, now)
        assert provider.entered.wait(timeout=3)
        deletion_future = pool.submit(_deletion_auth, client, pair["access_token"])
        time.sleep(0.15)
        assert not deletion_future.done()
        provider.release.set()
        worker_future.result(timeout=5)
        deletion_response = deletion_future.result(timeout=10)
    assert deletion_response.status_code == 204
    assert len(provider.sent) == 1
    _send_one(engine, delivery_id, settings, provider, now)
    run_once(engine, settings, provider, now)
    assert len(provider.sent) == 1
