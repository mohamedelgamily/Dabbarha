from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time as monotonic_time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.notification_copy import render_copy
from app.core.notification_settings import NotificationSettings
from app.core.notification_time import local_datetime, quiet_adjust
from app.core.security import create_access_token
from app.db.database import Base, create_app_engine
from app.main import app
from app.models.auth_session import AuthSession
from app.models.notifications import (
    Notification, NotificationDelivery, NotificationPreference,
    PaymentOccurrence, PaymentOccurrenceEvent, PushDevice,
)
from app.models.obligation import Obligation, ObligationInstallment
from app.models.user import User
from app.models.admin_operations import WorkerHeartbeat
from app.services.notification_worker import _claim_batch, _current_notification, materialize_due_deliveries, run_once
from app.services.notifications import (
    decrypt_push_token, encrypt_push_token, materialize_occurrence,
    synchronize_user,
)
from app.services.payment_occurrences import clamped_due_date, expected_occurrences
from app.services.push_provider import ExpoPushAdapter, MockPushAdapter, SendResult
from app.schemas.notifications import NotificationPreferencesUpdate, PushDeviceCreate
from tests.postgres_test_support import initialize_disposable_postgres


@pytest.fixture(scope="module")
def notification_postgres_service():
    binary_dir = os.environ.get("POSTGRES_TEST_BIN")
    if not binary_dir:
        if os.environ.get("REQUIRE_POSTGRES_TESTS") == "1":
            pytest.fail("POSTGRES_TEST_BIN is required for notification worker concurrency tests.")
        pytest.skip("Set POSTGRES_TEST_BIN for disposable PostgreSQL worker tests.")
    import psycopg
    with tempfile.TemporaryDirectory(prefix="dabbarha-notify-pg-", dir="/tmp") as directory:
        root = Path(directory)
        initialize_disposable_postgres(binary_dir, root / "data", root)
        with (root/"server.log").open("w") as log:
            proc = subprocess.Popen([str(Path(binary_dir)/"postgres"), "-D", str(root/"data"),
                "-k", directory, "-h", "", "-c", "unix_socket_permissions=0700"], stdout=log, stderr=log)
            try:
                deadline = monotonic_time.monotonic() + 15
                while True:
                    try:
                        with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test"):
                            break
                    except psycopg.Error:
                        if proc.poll() is not None or monotonic_time.monotonic() > deadline:
                            pytest.fail("Disposable PostgreSQL did not start (output suppressed).")
                        monotonic_time.sleep(.05)
                yield directory
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=5)


@pytest.fixture
def notify_db(tmp_path):
    engine = create_app_engine(f"sqlite:///{tmp_path / 'notifications.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def notify_api(notify_db, monkeypatch):
    key = secrets.token_bytes(32)
    settings = NotificationSettings(enabled=True, token_key=key)
    monkeypatch.setattr(app.state, "notification_settings", settings)
    with Session(notify_db) as db:
        user = User(name="Reminder Test", email="reminder@example.test", password_hash="not-used")
        other = User(name="Other", email="other-reminder@example.test", password_hash="not-used")
        db.add_all([user, other]); db.commit(); db.refresh(user); db.refresh(other)
        user_id, other_id = user.id, other.id
    def override_db():
        with Session(notify_db) as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, notify_db, f"Bearer {create_access_token(str(user_id))}", user_id, other_id
    finally:
        app.dependency_overrides.clear()


def legacy_obligation(user_id: int, **changes):
    values = dict(
        user_id=user_id, provider="Provider", item_name="Phone", category="device",
        total_amount=Decimal("1200.00"), monthly_installment_amount=Decimal("100.00"),
        start_date=date(2024, 1, 1), term_months=12, due_day_of_month=31,
        status="active", source="manual_entry",
    )
    values.update(changes)
    return Obligation(**values)


def test_legacy_day_31_clamps_and_february_leap_date_is_correct():
    assert clamped_due_date(2024, 2, 31) == date(2024, 2, 29)
    assert clamped_due_date(2025, 2, 31) == date(2025, 2, 28)


def test_occurrence_projection_uses_clamped_legacy_dates_and_exact_plan_dates(notify_db):
    with Session(notify_db) as db:
        user = User(name="Projection", email="projection@example.test", password_hash="x")
        db.add(user); db.flush()
        old = legacy_obligation(user.id, start_date=date(2024, 1, 1), term_months=3)
        exact = Obligation(user_id=user.id, provider="P", item_name="Plan", category="x",
                           total_amount=Decimal("20.00"), monthly_installment_amount=Decimal("10.00"),
                           purchase_price=Decimal("20.00"), payment_method="manual", interest_method="none",
                           down_payment_amount=Decimal("0.00"), down_payment_paid=False, schedule_version=1,
                           start_date=date(2025, 1, 1), term_months=2, due_day_of_month=31,
                           status="active", source="manual_entry")
        exact.installments = [
            ObligationInstallment(installment_number=1, due_date=date(2025, 1, 30), scheduled_amount=Decimal("11.00")),
            ObligationInstallment(installment_number=2, due_date=date(2025, 2, 27), scheduled_amount=Decimal("9.00")),
        ]
        db.add_all([old, exact]); db.commit(); db.refresh(old); db.refresh(exact)
        legacy = expected_occurrences(old, date(2024, 2, 1), date(2024, 2, 29))
        assert [(row.due_date, row.amount) for row in legacy] == [(date(2024, 2, 29), Decimal("100.00"))]
        exact_rows = expected_occurrences(exact, date(2025, 2, 1), date(2025, 2, 28))
        assert [(row.due_date, row.amount, row.installment_id) for row in exact_rows] == [
            (date(2025, 2, 27), Decimal("9.00"), exact.installments[1].id)
        ]


def test_payment_occurrence_mark_undo_audit_and_cross_user_isolation(notify_api):
    client, engine, auth, user_id, other_id = notify_api
    with Session(engine) as db:
        obligation = legacy_obligation(user_id, start_date=date(2024, 1, 1), term_months=3)
        db.add(obligation); db.commit(); db.refresh(obligation)
        occurrence = materialize_occurrence(db, obligation,
            expected_occurrences(obligation, date(2024, 2, 1), date(2024, 2, 29))[0])
        occurrence_id, obligation_id = occurrence.id, obligation.id
        db.commit()
    url = f"/obligations/{obligation_id}/payment-occurrences/{occurrence_id}"
    denied = client.post(url + "/mark-paid", headers={"Authorization": f"Bearer {create_access_token(str(other_id))}"})
    assert denied.status_code == 404
    marked = client.post(url + "/mark-paid", headers={"Authorization": auth})
    assert marked.status_code == 200 and marked.json()["state"] == "paid"
    undone = client.post(url + "/undo-paid", headers={"Authorization": auth})
    assert undone.status_code == 200 and undone.json()["state"] == "unpaid"
    with Session(engine) as db:
        row = db.get(PaymentOccurrence, occurrence_id)
        actions = db.scalars(select(PaymentOccurrenceEvent.action).where(
            PaymentOccurrenceEvent.occurrence_id == occurrence_id).order_by(PaymentOccurrenceEvent.id)).all()
        assert row.reminder_epoch == 1
        assert actions == ["marked_paid", "undone"]


def test_mark_paid_cancels_queued_reminder_and_down_payment_updates_compat_flag(notify_api):
    client, engine, auth, user_id, _ = notify_api
    with Session(engine) as db:
        obligation = legacy_obligation(user_id)
        db.add(obligation); db.flush()
        occurrence = materialize_occurrence(db, obligation,
            expected_occurrences(obligation, date(2024, 1, 1), date(2024, 1, 31))[0])
        row = Notification(user_id=user_id, obligation_id=obligation.id, occurrence_id=occurrence.id,
                           notification_type="upcoming", deduplication_key="test-cancel-reminder",
                           scheduled_at=datetime.now(timezone.utc), title="Reminder", body="Due soon",
                           route=f"/obligations/{obligation.id}", delivery_state="queued")
        db.add(row); db.commit(); occurrence_id, obligation_id, notification_id = occurrence.id, obligation.id, row.id
    response = client.post(f"/obligations/{obligation_id}/payment-occurrences/{occurrence_id}/mark-paid",
                           headers={"Authorization": auth})
    assert response.status_code == 200
    with Session(engine) as db:
        assert db.get(Notification, notification_id).delivery_state == "cancelled"
        assert db.get(Obligation, obligation_id).down_payment_paid is False


def test_notification_preferences_validation_and_safe_defaults(notify_api):
    client, _, auth, _, _ = notify_api
    response = client.get("/notifications/preferences", headers={"Authorization": auth})
    assert response.status_code == 200
    assert response.json()["timezone"] == "Africa/Cairo"
    assert response.json()["reminders_enabled"] is False
    assert response.json()["privacy_mode"] == "private"
    update_body = {
        "reminders_enabled": True, "reminder_offsets": [7, 3, 1, 0], "reminder_time": "09:00",
        "timezone": "Africa/Cairo", "quiet_start": "22:00", "quiet_end": "07:00",
        "language": "ar", "privacy_mode": "private", "overdue_enabled": False,
        "categories": ["upcoming", "due_today"],
    }
    assert client.put("/notifications/preferences", json=update_body, headers={"Authorization": auth}).status_code == 200
    update_body["timezone"] = "Mars/Olympus"
    assert client.put("/notifications/preferences", json=update_body, headers={"Authorization": auth}).status_code == 422
    update_body["timezone"] = "Africa/Cairo"
    update_body["quiet_end"] = None
    assert client.put("/notifications/preferences", json=update_body, headers={"Authorization": auth}).status_code == 422
    with pytest.raises(Exception):
        NotificationPreferencesUpdate(timezone="../../etc/passwd")


def test_timezone_and_quiet_hours_are_deterministic():
    from zoneinfo import ZoneInfo
    assert quiet_adjust(date(2026, 5, 4), time(23, 15), time(22), time(7)) == (date(2026, 5, 5), time(7))
    assert quiet_adjust(date(2026, 5, 4), time(6, 15), time(22), time(7)) == (date(2026, 5, 4), time(7))
    # New York spring-forward gap is shifted to the first valid wall minute.
    value = local_datetime(date(2026, 3, 8), time(2, 30), ZoneInfo("America/New_York"))
    assert (value.astimezone(ZoneInfo("America/New_York")).hour,
            value.astimezone(ZoneInfo("America/New_York")).minute) == (3, 0)


def test_encrypted_push_token_never_round_trips_as_database_plaintext():
    settings = NotificationSettings(enabled=True, token_key=secrets.token_bytes(32))
    token = "ExpoPushToken[Abcdefghijklmnopqrstuvwxyz1234567890]"
    schema = PushDeviceCreate(token=token, platform="ios")
    token_hash, ciphertext, nonce = encrypt_push_token(settings, schema.token, 7, "session-1")
    device = PushDevice(id=9, user_id=7, session_id="session-1", token_hash=token_hash,
                        token_ciphertext=ciphertext, token_nonce=nonce,
                        token_key_id=settings.token_key_id, platform="ios", active=True)
    assert decrypt_push_token(settings, device) == token
    assert token.encode() not in ciphertext and token_hash != token


def test_privacy_modes_and_english_arabic_templates_are_safe():
    private = render_copy("upcoming", "en", "private", item_name="Phone", amount=Decimal("123.45"), days=3)
    detailed = render_copy("upcoming", "en", "detailed", item_name="Phone", amount=Decimal("123.45"), days=3)
    arabic = render_copy("upcoming", "ar", "private", item_name="Phone", amount=Decimal("123.45"), days=3)
    assert "Phone" not in private[1] and "123.45" not in private[1]
    assert "Phone" in detailed[1] and "123.45" in detailed[1]
    assert "٣" in arabic[0] and "123.45" not in arabic[1]
    assert "marked" in render_copy("payment_completed", "en", "private", item_name="x", amount=Decimal("1"))[1]


def test_expo_adapter_ticket_receipt_and_bounded_transient_classification():
    def ok_handler(request):
        if request.url.path.endswith("/send"):
            return httpx.Response(200, json={"data": {"status": "ok", "id": "ticket-1"}})
        return httpx.Response(200, json={"data": {"ticket-1": {"status": "ok"}}})
    client = httpx.Client(transport=httpx.MockTransport(ok_handler))
    adapter = ExpoPushAdapter("", client=client)
    sent = adapter.send("ExpoPushToken[redacted-example]", "Title", "Body", {"route": "/obligations/1"})
    assert sent.accepted and sent.ticket_id == "ticket-1"
    assert adapter.receipts(["ticket-1"]) == {"ticket-1": {"status": "ok"}}
    adapter.close()

    def busy_handler(_request):
        return httpx.Response(429)
    adapter = ExpoPushAdapter("", client=httpx.Client(transport=httpx.MockTransport(busy_handler)))
    result = adapter.send("ExpoPushToken[redacted-example]", "Title", "Body", {})
    assert result.retryable and not result.accepted
    adapter.close()

    def timeout_handler(_request):
        raise httpx.ReadTimeout("redacted")
    adapter = ExpoPushAdapter("", client=httpx.Client(transport=httpx.MockTransport(timeout_handler)))
    result = adapter.send("ExpoPushToken[redacted-example]", "Title", "Body", {})
    assert result.error_code == "delivery_outcome_unknown" and not result.retryable
    adapter.close()


def test_worker_materializes_once_and_respects_paid_state(tmp_path):
    engine = create_app_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc)
    token_key = secrets.token_bytes(32)
    settings = NotificationSettings(enabled=True, delivery_enabled=True, token_key=token_key,
                                    receipt_after_seconds=900)
    provider = MockPushAdapter()
    try:
        with Session(engine) as db:
            user = User(name="Worker", email="worker@example.test", password_hash="x")
            db.add(user); db.flush()
            obligation = legacy_obligation(user.id, start_date=date(2026, 11, 1), term_months=2, due_day_of_month=1)
            db.add(obligation)
            session = AuthSession(id="device-session", user_id=user.id, created_at=int(now.timestamp()),
                                  last_refreshed_at=int(now.timestamp()), idle_expires_at=int((now+timedelta(days=30)).timestamp()),
                                  absolute_expires_at=int((now+timedelta(days=90)).timestamp()), revoked_at=None,
                                  revocation_reason=None, current_refresh_hash="a"*64, current_generation=0)
            db.add(session)
            pref = NotificationPreference(user_id=user.id, reminders_enabled=True, reminder_offsets=[7, 3, 1, 0],
                                          reminder_time="09:00", timezone="Africa/Cairo", quiet_start="22:00",
                                          quiet_end="07:00", language="en", privacy_mode="private",
                                          overdue_enabled=False, categories=["upcoming", "due_today"])
            db.add(pref); db.flush()
            token = "ExpoPushToken[Abcdefghijklmnopqrstuvwxyz1234567890]"
            digest, encrypted, nonce = encrypt_push_token(settings, token, user.id, session.id)
            device = PushDevice(user_id=user.id, session_id=session.id, token_hash=digest,
                                token_ciphertext=encrypted, token_nonce=nonce, token_key_id="v1",
                                platform="ios", active=True)
            db.add(device); db.commit()
            user_id, occurrence_date = user.id, date(2026, 11, 1)
        with Session(engine) as db:
            synchronize_user(db, user_id, now)
            db.commit()
        # The seven-day occurrence is scheduled for Cairo 09:00, which is later than now.
        result = run_once(engine, settings, provider, now)
        assert provider.sent == []
        scheduled = datetime(2026, 10, 25, 6, 0, tzinfo=timezone.utc)
        run_once(engine, settings, provider, scheduled)
        assert len(provider.sent) == 1
        with Session(engine) as db:
            pref = db.get(NotificationPreference, user_id)
            occurrence = db.scalar(select(PaymentOccurrence).where(PaymentOccurrence.user_id == user_id))
            event_row = db.scalar(select(Notification).where(Notification.occurrence_id == occurrence.id,
                                                              Notification.notification_type == "upcoming"))
            assert occurrence.due_date == occurrence_date and event_row.delivery_state == "accepted"
            event_row_id = event_row.id
            occurrence.state = "paid"
            pref.categories = ["upcoming", "due_today", "payment_completed"]
            completed = Notification(
                user_id=user_id, obligation_id=occurrence.obligation_id, occurrence_id=occurrence.id,
                notification_type="payment_completed", deduplication_key="completed-recovery-race-test",
                scheduled_at=scheduled, title="Marked paid", body="You marked this payment as paid.",
                route="obligation_detail", delivery_state="queued",
            )
            db.add(completed)
            db.commit()
            db.refresh(completed)
            assert _current_notification(db, completed, scheduled) is True
            occurrence.state = "unpaid"
            db.commit()
            assert _current_notification(db, completed, scheduled) is False
        later = scheduled + timedelta(seconds=1)
        run_once(engine, settings, provider, later)
        assert len(provider.sent) == 1
        with Session(engine) as db:
            delivery = db.scalar(select(NotificationDelivery).where(NotificationDelivery.notification_id == event_row_id))
            assert delivery.delivery_state == "accepted"
            heartbeat = db.get(WorkerHeartbeat, "notification-worker")
            assert heartbeat is not None and heartbeat.cycle_count >= 3
            assert heartbeat.last_success_at is not None and heartbeat.last_error_category is None
    finally:
        engine.dispose()


def test_expired_worker_send_is_not_retried_as_duplicate(notify_db):
    # A transport timeout has an ambiguous outcome; the adapter intentionally makes
    # it terminal rather than resending an alert that the provider may have accepted.
    provider = MockPushAdapter(SendResult(False, retryable=False, error_code="delivery_outcome_unknown"))
    result = provider.send("opaque", "title", "body", {})
    assert not result.accepted and not result.retryable


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_concurrent_workers_atomically_claim_one_delivery(backend, tmp_path, request):
    if backend == "sqlite":
        engine = create_app_engine(f"sqlite:///{tmp_path / 'claim.db'}")
    else:
        import psycopg
        from psycopg import sql
        directory = request.getfixturevalue("notification_postgres_service")
        database = "notify_" + uuid4().hex
        with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test", autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(database)))
        url = URL.create("postgresql+psycopg", username="dabbarha_test", database=database,
                         query={"host": directory}).render_as_string(hide_password=False)
        engine = create_app_engine(url)
    Base.metadata.create_all(engine)
    now = datetime(2026, 10, 24, 7, 0, tzinfo=timezone.utc)
    settings = NotificationSettings(enabled=True, delivery_enabled=True, token_key=secrets.token_bytes(32))
    try:
        with Session(engine) as db:
            user = User(name="Race", email=f"race-{backend}@example.test", password_hash="x")
            db.add(user); db.flush()
            obligation = legacy_obligation(user.id, start_date=date(2026, 10, 1), term_months=12, due_day_of_month=24)
            db.add(obligation)
            session = AuthSession(id="race-session", user_id=user.id, created_at=int(now.timestamp()),
                                  last_refreshed_at=int(now.timestamp()), idle_expires_at=int((now+timedelta(days=30)).timestamp()),
                                  absolute_expires_at=int((now+timedelta(days=90)).timestamp()), revoked_at=None,
                                  revocation_reason=None, current_refresh_hash="b"*64, current_generation=0)
            db.add(session)
            db.add(NotificationPreference(user_id=user.id, reminders_enabled=True, reminder_offsets=[0],
                                          reminder_time="09:00", timezone="Africa/Cairo", quiet_start=None,
                                          quiet_end=None, language="en", privacy_mode="private",
                                          overdue_enabled=False, categories=["due_today"]))
            db.flush()
            token = "ExpoPushToken[Abcdefghijklmnopqrstuvwxyz1234567890]"
            digest, encrypted, nonce = encrypt_push_token(settings, token, user.id, session.id)
            db.add(PushDevice(user_id=user.id, session_id=session.id, token_hash=digest,
                              token_ciphertext=encrypted, token_nonce=nonce, token_key_id="v1",
                              platform="android", active=True))
            db.commit()
            user_id = user.id
        from app.services.notifications import synchronize_user
        with Session(engine) as db:
            synchronize_user(db, user_id, now); db.commit()
        materialize_due_deliveries(engine, now)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: _claim_batch(engine, now, settings), range(2)))
        assert sum(len(result) for result in results) == 1
    finally:
        engine.dispose()
        if backend == "postgres":
            with psycopg.connect(host=directory, dbname="postgres", user="dabbarha_test", autocommit=True) as conn:
                conn.execute(sql.SQL("DROP DATABASE {} ").format(sql.Identifier(database)))
