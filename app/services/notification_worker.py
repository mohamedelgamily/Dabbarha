"""Database-backed notification scheduler and delivery worker.

Run as a separate process. No FastAPI BackgroundTasks, timers in web workers,
Redis queue, or provider call is started by importing the API application.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from app.db.account_lock import lock_account_row
from app.core.notification_time import safe_now
from app.models.auth_session import AuthSession
from app.models.notifications import (
    Notification, NotificationDelivery, NotificationPreference,
    PaymentOccurrence, PushDevice,
)
from app.services.notifications import decrypt_push_token, synchronize_user


RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 1800


def _sessions(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _upsert_delivery(db: Session, notification_id: int, device_id: int) -> None:
    values = {"notification_id": notification_id, "device_id": device_id,
              "delivery_state": "queued", "attempt_count": 0}
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(pg_insert(NotificationDelivery).values(**values).on_conflict_do_nothing(
            constraint="uq_notification_delivery_device"))
    elif bind.dialect.name == "sqlite":
        db.execute(sqlite_insert(NotificationDelivery).values(**values).on_conflict_do_nothing(
            index_elements=["notification_id", "device_id"]))
    elif db.scalar(select(NotificationDelivery.id).where(
        NotificationDelivery.notification_id == notification_id,
        NotificationDelivery.device_id == device_id,
    )) is None:
        db.add(NotificationDelivery(**values))


def _cancel_notification(db: Session, row: Notification, code: str) -> None:
    db.execute(update(NotificationDelivery).where(
        NotificationDelivery.notification_id == row.id,
        NotificationDelivery.delivery_state.in_(["queued", "sending"]),
    ).values(delivery_state="cancelled", error_code=code, lease_until=None))
    if row.delivery_state in {"queued", "sending"}:
        row.delivery_state = "cancelled"


def _current_notification(db: Session, row: Notification, now: datetime) -> bool:
    pref = db.get(NotificationPreference, row.user_id)
    if pref is None:
        return False
    if row.notification_type == "payment_completed":
        if not pref.reminders_enabled or "payment_completed" not in pref.categories:
            return False
        occurrence = db.get(PaymentOccurrence, row.occurrence_id) if row.occurrence_id is not None else None
        # A completion acknowledgement is valid only while the user's current
        # declaration remains paid. This also closes the race where undo-paid
        # lands after a worker queued the push but before it claims the delivery.
        return occurrence is not None and occurrence.state == "paid"
    if not pref.reminders_enabled or row.occurrence_id is None:
        return False
    occurrence = db.get(PaymentOccurrence, row.occurrence_id)
    if occurrence is None or occurrence.state != "unpaid":
        return False
    from zoneinfo import ZoneInfo
    local_today = now.astimezone(ZoneInfo(pref.timezone)).date()
    if row.notification_type == "upcoming":
        return occurrence.due_date > local_today and safe_now(row.scheduled_at).astimezone(ZoneInfo(pref.timezone)).date() == local_today
    if row.notification_type == "due_today":
        return occurrence.due_date == local_today
    if row.notification_type == "overdue":
        return occurrence.due_date + timedelta(days=1) == local_today and pref.overdue_enabled
    return False


def synchronize_schedules(engine, now: datetime | None = None) -> int:
    now = safe_now(now)
    factory = _sessions(engine)
    count = 0
    with factory.begin() as db:
        user_ids = db.scalars(select(NotificationPreference.user_id).where(
            NotificationPreference.reminders_enabled.is_(True))).all()
        for user_id in user_ids:
            count += synchronize_user(db, user_id, now)
    return count


def materialize_due_deliveries(engine, now: datetime | None = None, batch_size: int = 500) -> int:
    now = safe_now(now)
    factory = _sessions(engine)
    created = 0
    with factory.begin() as db:
        rows = db.scalars(select(Notification).where(
            Notification.scheduled_at <= now,
            Notification.delivery_state.in_(["queued", "sending"]),
        ).order_by(Notification.scheduled_at, Notification.id).limit(batch_size).with_for_update(skip_locked=True)).all()
        for row in rows:
            if not _current_notification(db, row, now):
                _cancel_notification(db, row, "notification_expired_or_no_longer_due")
                continue
            active_devices = db.execute(
                select(PushDevice.id).join(AuthSession, AuthSession.id == PushDevice.session_id).where(
                    PushDevice.user_id == row.user_id,
                    PushDevice.active.is_(True),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.idle_expires_at > int(now.timestamp()),
                    AuthSession.absolute_expires_at > int(now.timestamp()),
                )
            ).scalars().all()
            for device_id in active_devices:
                _upsert_delivery(db, row.id, device_id)
                created += 1
    return created


def _claim_batch(engine, now: datetime, settings) -> list[int]:
    factory = _sessions(engine)
    claimed: list[int] = []
    with factory() as db:
        stale_ids = db.scalars(select(NotificationDelivery.id).where(
            NotificationDelivery.delivery_state == "sending",
            NotificationDelivery.lease_until <= now,
        ).limit(settings.worker_batch_size)).all()
        candidate_ids = db.scalars(select(NotificationDelivery.id).join(Notification).where(
            NotificationDelivery.delivery_state == "queued",
            or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= now),
            Notification.scheduled_at <= now,
        ).order_by(Notification.scheduled_at, NotificationDelivery.id).limit(settings.worker_batch_size)).all()
    # A conditional UPDATE is the claim primitive on both databases. PostgreSQL
    # serializes conflicting row updates; SQLite serializes writers. Only one worker
    # can change a row from queued to sending and receive rowcount=1.
    for stale_id in stale_ids:
        with factory.begin() as db:
            changed = db.execute(update(NotificationDelivery).where(
                NotificationDelivery.id == stale_id,
                NotificationDelivery.delivery_state == "sending",
                NotificationDelivery.lease_until <= now,
            ).values(delivery_state="failed", error_code="delivery_outcome_unknown", lease_until=None)).rowcount
            if changed:
                delivery = db.get(NotificationDelivery, stale_id)
                if delivery is not None:
                    _refresh_notification_state(db, delivery.notification_id)
    for delivery_id in candidate_ids:
        with factory.begin() as db:
            changed = db.execute(update(NotificationDelivery).where(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.delivery_state == "queued",
                or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= now),
            ).values(delivery_state="sending", attempt_count=NotificationDelivery.attempt_count + 1,
                     last_attempt_at=now, lease_until=now + timedelta(seconds=settings.lease_seconds))).rowcount
            if changed != 1:
                continue
            delivery = db.get(NotificationDelivery, delivery_id)
            if delivery is None:
                continue
            notification = db.get(Notification, delivery.notification_id)
            if notification is None or not _current_notification(db, notification, now):
                if notification is not None:
                    _cancel_notification(db, notification, "notification_expired_or_no_longer_due")
                delivery.delivery_state = "cancelled"
                delivery.error_code = "notification_expired_or_no_longer_due"
                continue
            device = db.get(PushDevice, delivery.device_id)
            session = db.get(AuthSession, device.session_id) if device else None
            if (device is None or not device.active or session is None or session.revoked_at is not None
                    or session.idle_expires_at <= int(now.timestamp())
                    or session.absolute_expires_at <= int(now.timestamp())):
                delivery.delivery_state = "cancelled"
                delivery.error_code = "device_session_inactive"
                continue
            notification.delivery_state = "sending"
            claimed.append(delivery.id)
    return claimed


def _refresh_notification_state(db: Session, notification_id: int) -> None:
    # Worker sessions use autoflush=False. Flush delivery transitions before
    # querying their aggregate state, or the parent can remain stuck at
    # "sending" even though this transaction has accepted/failed the delivery.
    db.flush()
    row = db.get(Notification, notification_id)
    if row is None or row.delivery_state == "cancelled":
        return
    states = db.scalars(select(NotificationDelivery.delivery_state).where(
        NotificationDelivery.notification_id == notification_id)).all()
    if not states:
        return
    if "sending" in states:
        row.delivery_state = "sending"
    elif "queued" in states:
        row.delivery_state = "queued"
    elif "accepted" in states:
        row.delivery_state = "accepted"
    elif "platform_accepted" in states:
        row.delivery_state = "platform_accepted"
    elif all(value == "cancelled" for value in states):
        row.delivery_state = "cancelled"
    else:
        row.delivery_state = "failed"


def _send_one(engine, delivery_id: int, settings, provider, now: datetime) -> None:
    factory = _sessions(engine)
    # Keep the per-user row lock from the last eligibility check until the
    # bounded provider request and its result are committed. Account deletion
    # takes this same lock, so no send can start after deletion commits. The
    # production Expo client has a five-second HTTP timeout.
    with factory.begin() as db:
        delivery = db.get(NotificationDelivery, delivery_id)
        if delivery is None or delivery.delivery_state != "sending":
            return
        notification = db.get(Notification, delivery.notification_id)
        if notification is None:
            return
        if not lock_account_row(db, notification.user_id):
            return
        # The conditional lock update may have waited behind a worker/deletion
        # transaction. Refresh rows before the final send decision.
        db.expire(delivery)
        delivery = db.get(NotificationDelivery, delivery_id)
        notification = db.get(Notification, delivery.notification_id) if delivery else None
        if (delivery is None or delivery.delivery_state != "sending"
                or notification is None or not _current_notification(db, notification, now)):
            if delivery is not None and delivery.delivery_state == "sending":
                delivery.delivery_state = "cancelled"
                delivery.error_code = "notification_no_longer_eligible"
                delivery.lease_until = None
                if notification is not None:
                    _cancel_notification(db, notification, "notification_no_longer_eligible")
            return
        device = db.get(PushDevice, delivery.device_id)
        session = db.get(AuthSession, device.session_id) if device is not None else None
        if (device is None or not device.active or session is None or session.revoked_at is not None
                or session.idle_expires_at <= int(now.timestamp())
                or session.absolute_expires_at <= int(now.timestamp())):
            delivery.delivery_state = "cancelled"
            delivery.error_code = "device_session_inactive"
            delivery.lease_until = None
            _refresh_notification_state(db, notification.id)
            return
        try:
            token = decrypt_push_token(settings, device)
        except Exception:
            delivery.delivery_state = "failed"
            delivery.error_code = "device_token_unavailable"
            delivery.lease_until = None
            _refresh_notification_state(db, notification.id)
            return
        result = provider.send(token, notification.title, notification.body,
                               {"notification_id": notification.id,
                                "route": notification.route,
                                "obligation_id": notification.obligation_id})
        delivery.lease_until = None
        if result.accepted:
            delivery.delivery_state = "accepted"
            delivery.provider_reference = result.ticket_id
            delivery.receipt_status = None
            delivery.next_attempt_at = now + timedelta(seconds=settings.receipt_after_seconds)
            delivery.error_code = None
        elif result.retryable and delivery.attempt_count < settings.max_attempts:
            delay = min(RETRY_BASE_SECONDS * (2 ** (delivery.attempt_count - 1)), RETRY_MAX_SECONDS)
            delivery.delivery_state = "queued"
            delivery.next_attempt_at = now + timedelta(seconds=delay)
            delivery.error_code = result.error_code or "temporary_provider_failure"
        else:
            delivery.delivery_state = "failed"
            delivery.next_attempt_at = None
            delivery.error_code = result.error_code or "provider_rejected"
            if result.error_code == "DeviceNotRegistered":
                device.active = False
        _refresh_notification_state(db, delivery.notification_id)


def process_receipts(engine, settings, provider, now: datetime | None = None) -> int:
    now = safe_now(now)
    factory = _sessions(engine)
    with factory() as db:
        candidate_ids = db.scalars(select(NotificationDelivery.id).where(
            NotificationDelivery.delivery_state == "accepted",
            NotificationDelivery.provider_reference.is_not(None),
            NotificationDelivery.next_attempt_at <= now,
        ).order_by(NotificationDelivery.next_attempt_at).limit(1000)).all()
    ids = []
    with factory.begin() as db:
        for delivery_id in candidate_ids:
            row = db.get(NotificationDelivery, delivery_id)
            if row is None or row.delivery_state != "accepted" or row.next_attempt_at is None or safe_now(row.next_attempt_at) > now:
                continue
            if row.receipt_attempt_count >= settings.receipt_max_attempts:
                row.delivery_state = "failed"
                row.error_code = "receipt_unavailable"
                row.next_attempt_at = None
                _refresh_notification_state(db, row.notification_id)
                continue
            # This conditional claim bounds receipt polling across workers.
            changed = db.execute(update(NotificationDelivery).where(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.delivery_state == "accepted",
                NotificationDelivery.next_attempt_at <= now,
            ).values(receipt_attempt_count=NotificationDelivery.receipt_attempt_count + 1,
                     next_attempt_at=now + timedelta(minutes=5))).rowcount
            if changed:
                row = db.get(NotificationDelivery, delivery_id)
                ids.append((delivery_id, row.provider_reference, row.last_attempt_at,
                            row.receipt_attempt_count + 1))
    if not ids:
        return 0
    try:
        receipts = provider.receipts([item[1] for item in ids])
    except Exception:
        # The poll lease was already advanced. The next attempt is delayed, and the
        # configured attempt bound eventually ends receipt polling safely.
        return len(ids)
    with factory.begin() as db:
        for delivery_id, ticket_id, sent_at, receipt_attempt_count in ids:
            row = db.scalar(select(NotificationDelivery).where(
                NotificationDelivery.id == delivery_id).with_for_update())
            if row is None or row.delivery_state != "accepted":
                continue
            receipt = receipts.get(ticket_id)
            if receipt is None:
                if receipt_attempt_count >= settings.receipt_max_attempts or (
                    sent_at and now - safe_now(sent_at) >= timedelta(seconds=settings.receipt_retention_seconds)
                ):
                    row.delivery_state = "failed"
                    row.error_code = "receipt_expired" if sent_at and now - safe_now(sent_at) >= timedelta(seconds=settings.receipt_retention_seconds) else "receipt_unavailable"
                    row.next_attempt_at = None
                else:
                    row.next_attempt_at = now + timedelta(minutes=5)
                _refresh_notification_state(db, row.notification_id)
                continue
            status = receipt.get("status") if isinstance(receipt, dict) else None
            if status == "ok":
                row.delivery_state = "platform_accepted"
                row.receipt_status = "ok"
                row.error_code = None
            else:
                details = receipt.get("details", {}) if isinstance(receipt, dict) else {}
                code = details.get("error") if isinstance(details, dict) else None
                row.delivery_state = "failed"
                row.receipt_status = "error"
                row.error_code = code if isinstance(code, str) and len(code) <= 64 else "provider_receipt_error"
                if code == "DeviceNotRegistered":
                    device = db.get(PushDevice, row.device_id)
                    if device is not None:
                        device.active = False
            row.next_attempt_at = None
            _refresh_notification_state(db, row.notification_id)
    return len(ids)


def run_once(engine, settings, provider, now: datetime | None = None) -> dict[str, int]:
    now = safe_now(now)
    if not settings.enabled:
        return {"scheduled": 0, "deliveries": 0, "receipts": 0}
    scheduled = synchronize_schedules(engine, now)
    if not settings.delivery_enabled:
        return {"scheduled": scheduled, "deliveries": 0, "receipts": 0}
    materialized = materialize_due_deliveries(engine, now, settings.worker_batch_size)
    delivery_ids = _claim_batch(engine, now, settings)
    for delivery_id in delivery_ids:
        _send_one(engine, delivery_id, settings, provider, now)
    receipt_count = process_receipts(engine, settings, provider, now)
    return {"scheduled": scheduled, "deliveries": len(delivery_ids), "receipts": receipt_count}
