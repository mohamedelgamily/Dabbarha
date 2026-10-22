from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from uuid import uuid4
from dataclasses import replace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.core.admin_settings import AdminSettings
from app.core.notification_settings import NotificationSettings
from app.core.session_settings import SessionSettings
from app.core.rate_limit import StoreUnavailable
from app.core.security import create_access_token
from app.db.database import Base, create_app_engine
from app.api.deps import get_db
from app.main import app
from app.models.admin_audit import AdminAuditEvent
from app.models.admin_operations import WorkerHeartbeat
from app.models.auth_session import AuthSession
from app.models.notifications import Notification, NotificationDelivery, PaymentOccurrence, PushDevice
from app.models.obligation import Obligation, ObligationInstallment
from app.models.admin_support import FinancialSupportGrant
from app.models.user import User
from app.services.sessions import SessionService
from app.services.admin_security import encrypt_totp_secret, generate_totp_secret, totp_code
from app.services.notification_worker import _record_worker_heartbeat
from tests.postgres_test_support import initialize_disposable_postgres


def bearer(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


@pytest.fixture(scope="module")
def ops_postgres_service():
    binary_dir = os.environ.get("POSTGRES_TEST_BIN")
    if not binary_dir:
        if os.environ.get("REQUIRE_POSTGRES_TESTS") == "1":
            pytest.fail("POSTGRES_TEST_BIN must identify disposable PostgreSQL binaries.")
        pytest.skip("Set POSTGRES_TEST_BIN for disposable PostgreSQL integration tests.")
    import psycopg
    with tempfile.TemporaryDirectory(prefix="dabbarha-admin-ops-pg-", dir="/tmp") as directory:
        root = Path(directory)
        initialize_disposable_postgres(binary_dir, root / "data", root)
        with (root / "server.log").open("w") as log:
            proc = subprocess.Popen([str(Path(binary_dir) / "postgres"), "-D", str(root / "data"),
                                     "-k", directory, "-h", "", "-c", "unix_socket_permissions=0700"],
                                    stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
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
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


@pytest.fixture(params=["sqlite", "postgres"])
def ops_database(tmp_path, request):
    if request.param == "sqlite":
        engine = create_app_engine(f"sqlite:///{tmp_path / 'admin-ops.db'}")
    else:
        import psycopg
        from psycopg import sql
        directory = request.getfixturevalue("ops_postgres_service")
        name = "admin_ops_" + uuid4().hex
        with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test", autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        engine = create_app_engine(URL.create("postgresql+psycopg", username="dabbarha_test", database=name,
                                              query={"host": directory,
                                                     "options": "-c timezone=Africa/Cairo"})
                                 .render_as_string(hide_password=False))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    if request.param == "postgres":
        with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test", autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def ops_client(ops_database, monkeypatch):
    engine = ops_database
    service = SessionService(SessionSettings(enabled=True, receipt_key=secrets.token_bytes(32)))
    monkeypatch.setattr(app.state, "sessions", service)
    def override():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with Session(engine) as db:
            user = User(name="Operations Owner", email="session@example.com", password_hash="hash")
            db.add(user)
            db.commit()
            user_id = user.id
        with TestClient(app) as client:
            yield client, engine, user_id, service
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def enrolled_ops_admin(ops_client, monkeypatch):
    client, engine, user_id, service = ops_client
    key = secrets.token_bytes(32)
    policy = AdminSettings(enabled=True, totp_encryption_key=key)
    monkeypatch.setattr(app.state, "admin_settings", policy)
    with Session(engine) as db:
        user = db.get(User, user_id)
        user.admin_role = "admin"
        secret = generate_totp_secret()
        user.admin_totp_nonce, user.admin_totp_ciphertext = encrypt_totp_secret(secret, user_id, policy)
        user.admin_totp_key_id = policy.totp_key_id
        db.commit()
    pair = service.create(engine, user_id, "ops-test")
    response = client.post("/admin/auth/step-up", json={"code": totp_code(secret, int(time.time()) // 30)},
                           headers=bearer(pair))
    assert response.status_code == 200
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    return client, engine, user_id, service, pair, headers


def test_operational_admin_metrics_are_accurate_and_do_not_expose_finances(enrolled_ops_admin, monkeypatch):
    client, engine, user_id, _, pair, headers = enrolled_ops_admin
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        other = User(name="Other Person", email="other@example.test", password_hash="never-return-this")
        db.add(other)
        obligation = Obligation(user_id=user_id, provider="Store", item_name="Phone", category="electronics",
                                total_amount=Decimal("1200.00"), monthly_installment_amount=Decimal("100.00"),
                                start_date=date.today(), term_months=12, due_day_of_month=1)
        db.add(obligation)
        db.flush()
        session = db.get(AuthSession, pair["session_id"])
        session.current_generation = 1
        session.last_refreshed_at = int(now.timestamp())
        device = PushDevice(user_id=user_id, session_id=session.id, token_hash="a" * 64,
                            token_ciphertext=b"cipher", token_nonce=b"n" * 12, token_key_id="v1",
                            platform="ios", active=True)
        db.add(device)
        for index, state in enumerate(("queued", "accepted", "failed", "cancelled", "platform_accepted")):
            notification = Notification(user_id=user_id, notification_type="upcoming",
                                         deduplication_key=f"ops-{index}", scheduled_at=now,
                                         title="Private title", body="Private body", delivery_state=state)
            db.add(notification)
            db.flush()
            db.add(NotificationDelivery(notification_id=notification.id, device_id=device.id,
                                        delivery_state=state, attempt_count=index,
                                        error_code="DeviceNotRegistered" if state == "failed" else None))
        db.commit()
    monkeypatch.setattr(app.state, "notification_settings", NotificationSettings(enabled=True, delivery_enabled=True))
    _record_worker_heartbeat(engine, now, True, {"scheduled": 4, "deliveries": 2, "receipts": 1})

    response = client.get("/admin/ops/overview?window_days=7", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accounts"]["total"] == 2
    assert body["accounts"]["registered_in_window"] == 2
    assert body["accounts"]["recently_refreshed_v2_session_accounts"] == 1
    assert body["accounts"]["deletions_in_window"] is None
    assert body["accounts"]["deletions_available"] is False
    assert body["obligations_total"] == 1
    assert body["notifications"]["pending"] == 1
    assert body["notifications"]["accepted"] == 2
    assert body["notifications"]["failed"] == 1
    assert body["notifications"]["cancelled"] == 1
    assert body["notifications"]["failed_error_categories"] == [{"category": "push_device_invalid", "count": 1}]
    assert body["worker"]["state"] == "available"
    assert "monthly_income" not in response.text
    assert "1200.00" not in response.text
    assert "Private title" not in response.text
    assert "Private body" not in response.text
    assert "never-return-this" not in response.text


def test_exact_account_lookup_and_bounded_readonly_diagnostics(enrolled_ops_admin):
    client, engine, user_id, _, pair, headers = enrolled_ops_admin
    with Session(engine) as db:
        user = db.get(User, user_id)
        user.monthly_income = Decimal("77777.77")
        db.commit()
    by_id = client.get(f"/admin/users/lookup?user_id={user_id}", headers=headers)
    by_email = client.get("/admin/users/lookup?email=SESSION%40EXAMPLE.COM", headers=headers)
    assert by_id.status_code == by_email.status_code == 200, by_email.text
    assert by_id.json()["email"] == "session@example.com"
    assert by_id.json()["account_state"] == "present"
    assert "monthly_income" not in by_id.text and "77777.77" not in by_id.text
    assert client.get("/admin/users/lookup?email=*.test", headers=headers).status_code == 422
    assert client.get("/admin/users/lookup?user_id=1&email=a%40b.test", headers=headers).status_code == 422
    assert client.get("/admin/users/lookup?email=missing%40example.com", headers=headers).status_code == 404

    sessions = client.get(f"/admin/users/{user_id}/sessions?limit=1", headers=headers)
    assert sessions.status_code == 200
    assert sessions.json()["items"][0]["session_id"] == pair["session_id"]
    assert "refresh_token" not in sessions.text and "token_ciphertext" not in sessions.text
    assert client.get(f"/admin/users/{user_id}/sessions?limit=101", headers=headers).status_code == 422
    with Session(engine) as db:
        events = db.scalars(select(AdminAuditEvent).where(AdminAuditEvent.target_user_id == user_id)).all()
        assert len(events) >= 3
        assert all(event.action == "admin_user_inspection" for event in events)


@pytest.mark.parametrize("path", ["/admin/ops/overview", "/admin/ops/health",
                                  "/admin/users/lookup?user_id=1", "/admin/notifications/deliveries"])
def test_ordinary_user_and_invalid_credentials_are_denied_and_audited(ops_client, monkeypatch, path):
    client, engine, user_id, service = ops_client
    monkeypatch.setattr(app.state, "admin_settings", AdminSettings(enabled=True,
        totp_encryption_key=secrets.token_bytes(32)))
    pair = service.create(engine, user_id, "ordinary")
    response = client.get(path, headers=bearer(pair))
    assert response.status_code == 403
    assert client.get(path).status_code == 401
    with Session(engine) as db:
        action = ("admin_overview" if "/ops/overview" in path else
                  "admin_health_check" if "/ops/health" in path else
                  "admin_user_lookup" if "/users/lookup" in path else
                  "admin_notification_inspection")
        events = db.scalars(select(AdminAuditEvent).where(AdminAuditEvent.action == action)).all()
        assert len(events) == 2
        assert all(event.outcome == "failure" for event in events)


def test_disabled_admin_system_stays_hidden(enrolled_ops_admin, monkeypatch):
    client, _, _, _, _, headers = enrolled_ops_admin
    monkeypatch.setattr(app.state, "admin_settings", AdminSettings(enabled=False))
    assert client.get("/admin/ops/overview", headers=headers).status_code == 404


def test_revoked_session_cannot_use_admin_stepup_token(enrolled_ops_admin):
    client, engine, user_id, service, pair, headers = enrolled_ops_admin
    service.revoke(engine, pair["session_id"], user_id)
    assert client.get("/admin/ops/overview", headers=headers).status_code == 401


def test_notification_diagnostics_are_paginated_and_redacted(enrolled_ops_admin):
    client, engine, user_id, _, pair, headers = enrolled_ops_admin
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        device = PushDevice(user_id=user_id, session_id=pair["session_id"], token_hash="b" * 64,
                            token_ciphertext=b"cipher", token_nonce=b"n" * 12, token_key_id="v1",
                            platform="android", active=True)
        db.add(device)
        db.flush()
        for index in range(3):
            notice = Notification(user_id=user_id, notification_type="due_today", deduplication_key=f"page-{index}",
                                  scheduled_at=now, title="secret title", body="secret body")
            db.add(notice)
            db.flush()
            db.add(NotificationDelivery(notification_id=notice.id, device_id=device.id,
                                        delivery_state="failed", error_code="some-private-provider-text"))
        db.commit()
    page = client.get("/admin/notifications/deliveries?state=failed&limit=2", headers=headers)
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None
    assert page.json()["items"][0]["error_category"] == "other"
    assert "secret title" not in page.text and "secret body" not in page.text
    assert "some-private-provider-text" not in page.text
    next_page = client.get(f"/admin/notifications/deliveries?state=failed&limit=2&after_id={page.json()['next_cursor']}",
                           headers=headers)
    assert len(next_page.json()["items"]) == 1
    global_page = client.get("/admin/notifications/deliveries?state=failed&limit=2", headers=headers)
    assert global_page.status_code == 200 and len(global_page.json()["items"]) == 2


def test_worker_heartbeat_success_failure_and_staleness(ops_database):
    now_utc = datetime.now(timezone.utc)
    now_cairo = now_utc.astimezone(ZoneInfo("Africa/Cairo"))
    failed_at_utc = now_utc + timedelta(seconds=5)
    _record_worker_heartbeat(ops_database, now_cairo, True,
                             {"scheduled": 3, "deliveries": 4, "receipts": 2})
    _record_worker_heartbeat(ops_database, failed_at_utc.astimezone(ZoneInfo("Africa/Cairo")), False)
    with Session(ops_database) as db:
        if db.get_bind().dialect.name == "postgresql":
            # PostgreSQL must preserve the instant independently of the
            # connection timezone used when it materializes timestamptz.
            db.execute(text("SET TIME ZONE 'Africa/Cairo'"))
        row = db.get(WorkerHeartbeat, "notification-worker")
        assert row is not None
        assert row.cycle_count == 2
        if row.last_success_at.tzinfo is None:
            # SQLite DateTime(timezone=True) stores naive UTC wall time.
            assert row.last_success_at.replace(tzinfo=timezone.utc) == now_utc
            assert row.last_seen_at.replace(tzinfo=timezone.utc) == failed_at_utc
        else:
            assert row.last_success_at.astimezone(timezone.utc) == now_utc
            assert row.last_seen_at.astimezone(timezone.utc) == failed_at_utc
        assert row.last_error_category == "worker_cycle_failed"
        assert (row.last_scheduled, row.last_deliveries, row.last_receipts) == (3, 4, 2)
        from app.services.admin_operations import _worker_state
        status = _worker_state(db, NotificationSettings(enabled=True, delivery_enabled=True),
                               failed_at_utc + timedelta(seconds=5))
        assert status["state"] == "degraded"
        assert status["last_seen_at"] == failed_at_utc.isoformat()
        assert status["last_success_at"] == now_utc.isoformat()
        stale = _worker_state(db, NotificationSettings(enabled=True, delivery_enabled=True),
                              failed_at_utc + timedelta(minutes=2))
        assert stale["state"] == "stale"
        assert stale["last_seen_at"] == failed_at_utc.isoformat()


def test_health_readiness_is_safe_and_worker_downtime_is_visible(enrolled_ops_admin, monkeypatch):
    client, engine, _, _, _, headers = enrolled_ops_admin
    response = client.get("/admin/ops/health", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["components"]["api"] == "available"
    assert body["components"]["database"] == "available"
    assert body["components"]["redis"] == "available"
    assert body["components"]["migration"] in {"available", "unknown"}
    assert "database_url" not in response.text and "totp_encryption_key" not in response.text

    monkeypatch.setattr(app.state, "notification_settings", NotificationSettings(enabled=True, delivery_enabled=True))
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    _record_worker_heartbeat(engine, stale_at.astimezone(ZoneInfo("Africa/Cairo")), True)
    stale = client.get("/admin/ops/health", headers=headers)
    assert stale.json()["worker"]["state"] == "stale"
    assert stale.json()["components"]["notification_worker"] == "stale"
    assert stale.json()["status"] == "degraded"
    assert stale.json()["worker"]["last_seen_at"] == stale_at.isoformat()
    assert stale.json()["worker"]["last_success_at"] == stale_at.isoformat()


def test_empty_overview_reports_zero_and_unavailable_deletion_metric(enrolled_ops_admin, monkeypatch):
    client, _, _, _, _, headers = enrolled_ops_admin
    monkeypatch.setattr(app.state, "notification_settings", NotificationSettings(enabled=False))
    response = client.get("/admin/ops/overview", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["obligations_total"] == 0
    assert body["notifications"]["queue_size"] == 0
    assert body["worker"]["state"] == "disabled"
    assert body["accounts"]["deletions_available"] is False
    assert body["accounts"]["deletions_in_window"] is None


def test_admin_requests_are_rate_limited_and_redis_failure_fails_closed(enrolled_ops_admin, monkeypatch):
    client, _, _, _, _, headers = enrolled_ops_admin
    runtime = app.state.security
    runtime.settings = replace(runtime.settings, admin_limit=1)
    assert client.get("/admin/ops/overview", headers=headers).status_code == 200
    assert client.get("/admin/ops/overview", headers=headers).status_code == 429

    runtime.limiter.store.admit = lambda *_args: (_ for _ in ()).throw(StoreUnavailable())
    failed = client.get("/admin/ops/health", headers=headers)
    assert failed.status_code == 503
    assert "redis" not in failed.text.lower() or "temporarily" in failed.text.lower()


def test_database_health_failure_is_redacted(enrolled_ops_admin, monkeypatch):
    import app.api.routes.admin as admin_routes
    client, _, _, _, _, headers = enrolled_ops_admin
    def unavailable(*_args, **_kwargs):
        raise OperationalError("SELECT secret", {}, RuntimeError("private connection detail"))
    monkeypatch.setattr(admin_routes, "system_health", unavailable)
    response = client.get("/admin/ops/health", headers=headers)
    assert response.status_code == 503
    assert "private connection detail" not in response.text
    assert "secret" not in response.text


@pytest.fixture
def enrolled_support_superadmin(ops_client, monkeypatch):
    client, engine, admin_id, service = ops_client
    key = secrets.token_bytes(32)
    policy = AdminSettings(enabled=True, totp_encryption_key=key)
    monkeypatch.setattr(app.state, "admin_settings", policy)
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        admin.admin_role = "superadmin"
        secret = generate_totp_secret()
        admin.admin_totp_nonce, admin.admin_totp_ciphertext = encrypt_totp_secret(secret, admin_id, policy)
        admin.admin_totp_key_id = policy.totp_key_id
        target = User(name="Support Target", email="support-target@example.com", password_hash="sensitive-hash")
        db.add(target)
        db.flush()
        target_id = target.id
        obligation = Obligation(user_id=target_id, provider="Provider", item_name="Phone", category="electronics",
            total_amount=Decimal("1200.00"), monthly_installment_amount=Decimal("100.00"),
            purchase_price=Decimal("1200.00"), payment_method="manual", interest_method="none",
            start_date=date(2026, 1, 1), term_months=12, due_day_of_month=1)
        db.add(obligation)
        db.flush()
        obligation_id = obligation.id
        db.add(ObligationInstallment(obligation_id=obligation_id, installment_number=1,
            due_date=date(2026, 1, 1), scheduled_amount=Decimal("100.00"),
            principal_amount=Decimal("100.00"), interest_amount=Decimal("0.00")))
        db.add(PaymentOccurrence(user_id=target_id, obligation_id=obligation_id,
            occurrence_key="schedule-v1-1", payment_kind="regular", due_date=date(2026, 1, 1),
            scheduled_amount=Decimal("100.00"), schedule_version=1, state="paid",
            paid_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        target.monthly_income = Decimal("7000.00")
        target.fixed_expenses = Decimal("3000.00")
        db.commit()
    pair = service.create(engine, admin_id, "support-test")
    now = int(time.time())
    response = client.post("/admin/auth/step-up", json={"code": totp_code(secret, now // 30)},
                           headers=bearer(pair))
    assert response.status_code == 200, response.text
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    return client, engine, admin_id, target_id, obligation_id, secret, headers


def _patch_support_clock(monkeypatch, support_admin, start=None):
    from types import SimpleNamespace
    import app.api.routes.admin_support as support_routes
    current = int(start or time.time())
    clock = {"now": current}
    monkeypatch.setattr(support_routes, "time", SimpleNamespace(time=lambda: clock["now"]))

    def fresh_headers():
        next_step = clock["now"] // 30 + 1
        clock["now"] = next_step * 30 + 1
        return {**support_admin[6], "X-Admin-TOTP": totp_code(support_admin[5], next_step)}
    return clock, fresh_headers


def _create_and_self_approve_support_grant(client, headers, target_id, scopes=None):
    body = {"target_user_id": target_id, "support_case_reference": "CASE-2026-123",
            "reason_code": "payment_question", "scopes": scopes or ["financial_profile", "obligations", "installments", "payment_statuses"]}
    created = client.post("/admin/support-grants", json=body, headers=headers)
    assert created.status_code == 201, created.text
    grant_id = created.json()["grant_id"]
    rejected_self_approval = client.post(f"/admin/support-grants/{grant_id}/approve",
                                         json={"self_approval": False}, headers=headers)
    assert rejected_self_approval.status_code == 422
    approved = client.post(f"/admin/support-grants/{grant_id}/approve", json={"self_approval": True}, headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["self_approved"] is True
    assert approved.json()["expires_at"] == created.json()["expires_at"]
    return grant_id


def test_support_grant_self_approval_scoped_reads_fresh_totp_and_privacy(enrolled_support_superadmin, monkeypatch):
    client, engine, admin_id, target_id, obligation_id, _, headers = enrolled_support_superadmin
    grant_id = _create_and_self_approve_support_grant(client, headers, target_id)
    _, next_headers = _patch_support_clock(monkeypatch, enrolled_support_superadmin)

    missing_totp = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile",
                              headers=headers)
    assert missing_totp.status_code == 403
    profile_headers = next_headers()
    profile = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile",
                         headers=profile_headers)
    assert profile.status_code == 200, profile.text
    assert profile.json() == {"target_user_id": target_id, "monthly_income": "7000.00",
                              "fixed_expenses": "3000.00", "currency": "EGP"}
    assert profile.headers["cache-control"] == "no-store"
    assert "sensitive-hash" not in profile.text and "password_hash" not in profile.text
    assert "token" not in profile.text.lower()
    assert "email" not in profile.json()

    reused = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile",
                        headers=profile_headers)
    assert reused.status_code == 403

    obligations = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/obligations?limit=1",
                             headers=next_headers())
    assert obligations.status_code == 200, obligations.text
    assert obligations.json()["items"][0]["total_amount"] == "1200.00"
    assert obligations.json()["items"][0]["monthly_installment_amount"] == "100.00"
    installments = client.get(
        f"/admin/support-grants/{grant_id}/users/{target_id}/obligations/{obligation_id}/installments?limit=1",
        headers=next_headers())
    assert installments.status_code == 200, installments.text
    assert installments.json()["items"][0]["scheduled_amount"] == "100.00"
    assert installments.json()["schedule_version"] == 0
    statuses = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/payment-statuses?limit=1",
                          headers=next_headers())
    assert statuses.status_code == 200, statuses.text
    assert statuses.json()["items"][0]["state"] == "paid"
    assert statuses.json()["items"][0]["scheduled_amount"] == "100.00"
    assert client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/obligations?limit=51",
                      headers=next_headers()).status_code == 422
    assert client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/obligations?offset=1001",
                      headers=next_headers()).status_code == 422
    with Session(engine) as db:
        grant = db.get(FinancialSupportGrant, grant_id)
        events = db.scalars(select(AdminAuditEvent).where(AdminAuditEvent.support_grant_id == grant_id)).all()
        assert grant is not None and grant.self_approved
        assert any(event.action == "support_grant_self_approval" and event.outcome == "success" for event in events)
        assert sum(event.action == "support_financial_read" for event in events) == 4
        assert any(event.action == "support_financial_denied" and event.outcome == "failure" for event in events)
        assert set(AdminAuditEvent.__table__.columns.keys()) == {
            "id", "actor_user_id", "target_user_id", "support_grant_id", "action",
            "outcome", "source_fingerprint", "created_at",
        }


def test_support_grant_target_scope_expiry_and_revocation_are_enforced(enrolled_support_superadmin, monkeypatch):
    client, engine, _, target_id, _, _, headers = enrolled_support_superadmin
    grant_id = _create_and_self_approve_support_grant(client, headers, target_id, ["financial_profile"])
    _, next_headers = _patch_support_clock(monkeypatch, enrolled_support_superadmin)
    wrong_target = client.get(f"/admin/support-grants/{grant_id}/users/{target_id + 1}/financial-profile",
                              headers=next_headers())
    assert wrong_target.status_code == 404
    out_of_scope = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/obligations",
                              headers=next_headers())
    assert out_of_scope.status_code == 403
    revoked = client.post(f"/admin/support-grants/{grant_id}/revoke", headers=headers)
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    denied = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile",
                        headers=next_headers())
    assert denied.status_code == 403
    with Session(engine) as db:
        assert db.get(FinancialSupportGrant, grant_id).status == "revoked"


def test_independent_superadmin_approval_keeps_access_bound_to_requester_session(enrolled_support_superadmin, monkeypatch):
    client, engine, requester_id, target_id, _, _, requester_headers = enrolled_support_superadmin
    created = client.post("/admin/support-grants", json={
        "target_user_id": target_id, "support_case_reference": "CASE-2026-456",
        "reason_code": "security_review", "scopes": ["financial_profile"],
    }, headers=requester_headers)
    assert created.status_code == 201, created.text
    grant_id = created.json()["grant_id"]
    policy = app.state.admin_settings
    with Session(engine) as db:
        approver = User(name="Independent Reviewer", email="second-superadmin@example.com", password_hash="hash")
        db.add(approver)
        db.flush()
        approver.admin_role = "superadmin"
        approver_secret = generate_totp_secret()
        approver.admin_totp_nonce, approver.admin_totp_ciphertext = encrypt_totp_secret(
            approver_secret, approver.id, policy)
        approver.admin_totp_key_id = policy.totp_key_id
        approver_id = approver.id
        db.commit()
    service = app.state.sessions
    approver_pair = service.create(engine, approver_id, "independent-review")
    stepup = client.post("/admin/auth/step-up", json={
        "code": totp_code(approver_secret, int(time.time()) // 30)}, headers=bearer(approver_pair))
    assert stepup.status_code == 200, stepup.text
    approver_headers = {"Authorization": "Bearer " + stepup.json()["access_token"]}
    approved = client.post(f"/admin/support-grants/{grant_id}/approve", json={}, headers=approver_headers)
    assert approved.status_code == 200 and approved.json()["self_approved"] is False
    _, fresh_headers = _patch_support_clock(monkeypatch, enrolled_support_superadmin)
    profile = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile",
                         headers=fresh_headers())
    assert profile.status_code == 200, profile.text
    with Session(engine) as db:
        grant = db.get(FinancialSupportGrant, grant_id)
        assert grant.requester_user_id == requester_id
        assert grant.approver_user_id == approver_id
        assert grant.requester_session_id != approver_pair["session_id"]
        assert grant.self_approved is False


def test_support_grant_duplicate_totp_is_atomic_across_concurrent_reads(enrolled_support_superadmin, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    client, _, _, target_id, _, _, headers = enrolled_support_superadmin
    grant_id = _create_and_self_approve_support_grant(client, headers, target_id, ["financial_profile"])
    _, next_headers = _patch_support_clock(monkeypatch, enrolled_support_superadmin)
    same_header = next_headers()
    path = f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.get(path, headers=same_header), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 403]


def test_support_grant_revoke_racing_read_blocks_future_reads(enrolled_support_superadmin, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    client, _, _, target_id, _, _, headers = enrolled_support_superadmin
    grant_id = _create_and_self_approve_support_grant(client, headers, target_id, ["financial_profile"])
    _, next_headers = _patch_support_clock(monkeypatch, enrolled_support_superadmin)
    read_headers = next_headers()
    read_path = f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile"
    revoke_path = f"/admin/support-grants/{grant_id}/revoke"
    with ThreadPoolExecutor(max_workers=2) as pool:
        read_future = pool.submit(client.get, read_path, headers=read_headers)
        revoke_future = pool.submit(client.post, revoke_path, headers=headers)
        read_response, revoke_response = read_future.result(), revoke_future.result()
    assert revoke_response.status_code == 200 and revoke_response.json()["status"] == "revoked"
    assert read_response.status_code in {200, 403}
    after = client.get(read_path, headers=next_headers())
    assert after.status_code == 403


def test_support_grant_expiry_and_role_change_block_reads(enrolled_support_superadmin, monkeypatch):
    client, engine, admin_id, target_id, _, secret, headers = enrolled_support_superadmin
    grant_id = _create_and_self_approve_support_grant(client, headers, target_id, ["financial_profile"])
    with Session(engine) as db:
        grant = db.get(FinancialSupportGrant, grant_id)
        grant.expires_at = int(time.time()) - 1
        db.commit()
    expired = client.get(f"/admin/support-grants/{grant_id}", headers=headers)
    assert expired.status_code == 200 and expired.json()["status"] == "expired"
    expired_revoke = client.post(f"/admin/support-grants/{grant_id}/revoke", headers=headers)
    assert expired_revoke.status_code == 200 and expired_revoke.json()["status"] == "expired"
    with Session(engine) as db:
        assert db.get(FinancialSupportGrant, grant_id).status == "expired"
        assert db.scalar(select(AdminAuditEvent.id).where(
            AdminAuditEvent.action == "support_grant_expired",
            AdminAuditEvent.support_grant_id == grant_id)) is not None
        admin = db.get(User, admin_id)
        admin.admin_role = "admin"
        db.commit()
    denied = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile",
                        headers={**headers, "X-Admin-TOTP": totp_code(secret, int(time.time()) // 30)})
    assert denied.status_code == 403


def test_target_account_deletion_removes_grants_and_unlinks_audit(enrolled_support_superadmin):
    client, engine, _, target_id, _, _, headers = enrolled_support_superadmin
    grant_id = _create_and_self_approve_support_grant(client, headers, target_id)
    with Session(engine) as db:
        db.execute(text("DELETE FROM users WHERE id = :target_id"), {"target_id": target_id})
        db.commit()
        assert db.get(FinancialSupportGrant, grant_id) is None
        events = db.scalars(select(AdminAuditEvent).where(AdminAuditEvent.action.like("support_%"))).all()
        assert events
        assert all(event.target_user_id is None and event.support_grant_id is None for event in events)
        assert db.scalar(select(Obligation.id).where(Obligation.user_id == target_id)) is None
        assert db.scalar(select(PaymentOccurrence.id).where(PaymentOccurrence.user_id == target_id)) is None


def test_support_grant_input_validation_and_operational_admin_denial(enrolled_ops_admin, ops_client):
    client, engine, admin_id, _, pair, headers = enrolled_ops_admin
    invalid = client.post("/admin/support-grants", json={
        "target_user_id": admin_id, "support_case_reference": "*", "reason_code": "other",
        "scopes": ["financial_profile", "financial_profile"],
    }, headers=headers)
    assert invalid.status_code == 422
    denied = client.post("/admin/support-grants", json={
        "target_user_id": admin_id, "support_case_reference": "CASE-123", "reason_code": "account_support",
        "scopes": ["financial_profile"],
    }, headers=headers)
    assert denied.status_code == 403
    normal_client, normal_engine, normal_user_id, normal_service = ops_client
    normal_pair = normal_service.create(normal_engine, normal_user_id, "ordinary")
    no_admin = normal_client.get("/admin/support-grants/not-a-grant", headers=bearer(normal_pair))
    assert no_admin.status_code == 403
    with Session(engine) as db:
        assert db.scalar(select(FinancialSupportGrant.id)) is None
        assert db.scalar(select(AdminAuditEvent.id).where(
            AdminAuditEvent.action == "support_financial_denied")) is not None


def test_support_financial_read_database_failure_is_safe_503(enrolled_support_superadmin, monkeypatch):
    import app.api.routes.admin_support as support_routes
    from sqlalchemy.exc import OperationalError
    client, _, _, target_id, _, _, headers = enrolled_support_superadmin
    grant_id = _create_and_self_approve_support_grant(client, headers, target_id, ["financial_profile"])

    def unavailable(*_args, **_kwargs):
        raise OperationalError("SELECT private", {}, RuntimeError("private database detail"))

    monkeypatch.setattr(support_routes, "select", unavailable)
    response = client.get(f"/admin/support-grants/{grant_id}/users/{target_id}/financial-profile",
                          headers={**headers, "X-Admin-TOTP": "000000"})
    assert response.status_code == 503
    assert "private database detail" not in response.text and "SELECT" not in response.text
