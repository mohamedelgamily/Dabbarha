"""Notification preferences, encrypted device tokens and durable schedule generation."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, selectinload

from app.core.notification_copy import COPY_VERSION, render_copy
from app.core.notification_time import local_datetime, quiet_adjust, safe_now
from app.core.receipts import ReceiptCipher
from app.models.auth_session import AuthSession
from app.models.notifications import (
    Notification, NotificationDelivery, NotificationPreference,
    PaymentOccurrence, PaymentOccurrenceEvent, PushDevice,
)
from app.models.obligation import Obligation
from app.services.payment_occurrences import expected_occurrences, materialize_occurrence

PUSH_TOKEN_PREFIXES = ("ExpoPushToken[", "ExponentPushToken[")


def require_enabled(settings) -> None:
    if not settings.enabled or len(settings.token_key) != 32:
        raise HTTPException(503, "Notification settings are unavailable. Please try again later.",
                            headers={"Retry-After": "1"})


def _aad(device: PushDevice) -> bytes:
    return (f"dabbarha-push-token-v1|{device.user_id}|{device.session_id}|{device.token_hash}|{device.token_key_id}").encode()


def encrypt_push_token(settings, token: str, user_id: int, session_id: str):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    nonce = secrets.token_bytes(12)
    aad = f"dabbarha-push-token-v1|{user_id}|{session_id}|{token_hash}|{settings.token_key_id}".encode()
    encrypted = ReceiptCipher(settings.token_key).encrypt(nonce, token.encode("utf-8"), aad)
    return token_hash, encrypted, nonce


def decrypt_push_token(settings, device: PushDevice) -> str:
    if device.token_key_id != settings.token_key_id or len(settings.token_key) != 32:
        raise ValueError("push token encryption key is unavailable")
    plaintext = ReceiptCipher(settings.token_key).decrypt(device.token_nonce, device.token_ciphertext, _aad(device))
    token = plaintext.decode("utf-8")
    if hashlib.sha256(token.encode("utf-8")).hexdigest() != device.token_hash:
        raise ValueError("push token integrity check failed")
    return token


def get_preferences(db: Session, user_id: int, *, create: bool = True) -> NotificationPreference | None:
    row = db.get(NotificationPreference, user_id)
    if row is not None or not create:
        return row
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(pg_insert(NotificationPreference).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"]))
    elif bind.dialect.name == "sqlite":
        db.execute(sqlite_insert(NotificationPreference).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"]))
    else:
        db.add(NotificationPreference(user_id=user_id))
        db.flush()
    return db.get(NotificationPreference, user_id)


def register_device(db: Session, settings, *, user_id: int, session_id: str, token: str, platform: str) -> PushDevice:
    require_enabled(settings)
    session = db.scalar(select(AuthSession).where(
        AuthSession.id == session_id, AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    ))
    if session is None:
        raise HTTPException(401, "An active device session is required.")
    token_hash, encrypted, nonce = encrypt_push_token(settings, token, user_id, session_id)
    device = db.scalar(select(PushDevice).where(PushDevice.token_hash == token_hash).with_for_update())
    if device is not None and device.user_id != user_id:
        raise HTTPException(409, "This device token is already registered.")
    if device is None:
        device = PushDevice(user_id=user_id, session_id=session_id, token_hash=token_hash,
                            token_ciphertext=encrypted, token_nonce=nonce,
                            token_key_id=settings.token_key_id, platform=platform, active=True)
        db.add(device)
    else:
        if device.session_id != session_id:
            db.execute(update(NotificationDelivery).where(
                NotificationDelivery.device_id == device.id,
                NotificationDelivery.delivery_state.in_(["queued", "sending"]),
            ).values(delivery_state="cancelled", error_code="device_session_changed"))
        device.session_id = session_id
        device.token_ciphertext = encrypted
        device.token_nonce = nonce
        device.token_key_id = settings.token_key_id
        device.platform = platform
        device.active = True
        device.last_registered_at = datetime.now(timezone.utc)
    db.flush()
    return device


def cancel_occurrence_notifications(db: Session, occurrence_ids: list[int]) -> None:
    if not occurrence_ids:
        return
    ids = select(Notification.id).where(
        Notification.occurrence_id.in_(occurrence_ids),
        Notification.delivery_state.in_(["queued", "sending"]),
    )
    db.execute(update(NotificationDelivery).where(
        NotificationDelivery.notification_id.in_(ids),
        NotificationDelivery.delivery_state.in_(["queued", "sending"]),
    ).values(delivery_state="cancelled", error_code="payment_state_changed", lease_until=None))
    db.execute(update(Notification).where(
        Notification.id.in_(ids), Notification.delivery_state.in_(["queued", "sending"]),
    ).values(delivery_state="cancelled"))


def cancel_user_reminders(db: Session, user_id: int) -> None:
    ids = select(Notification.id).where(Notification.user_id == user_id,
                                        Notification.delivery_state.in_(["queued", "sending"]))
    db.execute(update(NotificationDelivery).where(
        NotificationDelivery.notification_id.in_(ids),
        NotificationDelivery.delivery_state.in_(["queued", "sending"]),
    ).values(delivery_state="cancelled", error_code="preferences_changed", lease_until=None))
    db.execute(update(Notification).where(Notification.id.in_(ids)).values(delivery_state="cancelled"))


def invalidate_obligation_schedule(db: Session, obligation: Obligation, *, remove: bool = False,
                                   supersede: bool = True) -> None:
    rows = list(db.scalars(select(PaymentOccurrence).where(
        PaymentOccurrence.obligation_id == obligation.id,
        PaymentOccurrence.state == "unpaid",
    ).with_for_update()).all())
    for row in rows:
        if supersede:
            row.state = "superseded"
        else:
            row.reminder_epoch += 1
    cancel_occurrence_notifications(db, [row.id for row in rows])
    if remove:
        db.execute(update(Notification).where(
            Notification.obligation_id == obligation.id,
            Notification.delivery_state.in_(["queued", "sending"]),
        ).values(delivery_state="cancelled"))


def _parse_time(value: str | None) -> time | None:
    return None if value is None else time.fromisoformat(value)


def _scheduled_utc(pref: NotificationPreference, day: date) -> datetime:
    local_day, local_time = quiet_adjust(day, _parse_time(pref.reminder_time),
                                         _parse_time(pref.quiet_start), _parse_time(pref.quiet_end))
    return local_datetime(local_day, local_time, ZoneInfo(pref.timezone))


def _insert_notification(db: Session, values: dict) -> Notification:
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(pg_insert(Notification).values(**values).on_conflict_do_nothing(
            constraint="uq_notification_deduplication_key"))
    elif bind.dialect.name == "sqlite":
        db.execute(sqlite_insert(Notification).values(**values).on_conflict_do_nothing(
            index_elements=["deduplication_key"]))
    else:
        existing = db.scalar(select(Notification).where(Notification.deduplication_key == values["deduplication_key"]))
        if existing is None:
            db.add(Notification(**values))
            db.flush()
    row = db.scalar(select(Notification).where(Notification.deduplication_key == values["deduplication_key"]).with_for_update())
    if row is not None and row.delivery_state == "cancelled" and values["scheduled_at"] >= safe_now():
        row.delivery_state = "queued"
        row.scheduled_at = values["scheduled_at"]
        row.title = values["title"]
        row.body = values["body"]
        row.route = values["route"]
        row.updated_at = safe_now()
    elif row is not None and row.delivery_state == "queued":
        row.scheduled_at = values["scheduled_at"]
        row.title = values["title"]
        row.body = values["body"]
        row.route = values["route"]
        row.updated_at = safe_now()
    if row is None:
        raise RuntimeError("Notification could not be materialized.")
    return row


def _schedule_occurrence(db: Session, pref: NotificationPreference, obligation: Obligation,
                         occurrence: PaymentOccurrence, now: datetime) -> int:
    local_now = now.astimezone(ZoneInfo(pref.timezone))
    today = local_now.date()
    kind = occurrence.payment_kind
    due_day = occurrence.due_date
    made = 0
    candidates: list[tuple[str, int | str, date, datetime]] = []
    if due_day >= today and "upcoming" in pref.categories:
        for offset in sorted(set(pref.reminder_offsets), reverse=True):
            if offset == 0 or due_day - timedelta(days=offset) < today:
                continue
            candidate = _scheduled_utc(pref, due_day - timedelta(days=offset))
            if candidate > now:
                candidates.append(("upcoming", offset, due_day - timedelta(days=offset), candidate))
        # One catch-up at most after downtime; do not replay every missed offset.
        if due_day > today and not candidates and any(due_day - timedelta(days=offset) < today for offset in pref.reminder_offsets if offset > 0):
            candidates.append(("upcoming", "catchup", today, now))
    if due_day == today and 0 in pref.reminder_offsets and "due_today" in pref.categories:
        when = _scheduled_utc(pref, today)
        candidates.append(("due_today", 0, today, max(when, now)))
    if pref.overdue_enabled and "overdue" in pref.categories and due_day < today and due_day + timedelta(days=1) == today:
        when = _scheduled_utc(pref, today)
        candidates.append(("overdue", 1, today, max(when, now)))

    for notification_type, offset, _local_day, scheduled_at in candidates:
        days = max(0, (due_day - scheduled_at.astimezone(ZoneInfo(pref.timezone)).date()).days)
        title, body = render_copy(notification_type, pref.language, pref.privacy_mode,
                                  item_name=obligation.item_name, amount=occurrence.scheduled_amount, days=days)
        dedupe = f"payment:{occurrence.id}:{occurrence.reminder_epoch}:{notification_type}:{offset}"
        _insert_notification(db, {
            "user_id": obligation.user_id, "obligation_id": obligation.id,
            "occurrence_id": occurrence.id, "notification_type": notification_type,
            "deduplication_key": dedupe, "scheduled_at": scheduled_at,
            "title": title, "body": body, "copy_version": COPY_VERSION,
            "route": "obligation_detail", "delivery_state": "queued",
        })
        made += 1
    return made


def synchronize_user(db: Session, user_id: int, now: datetime | None = None) -> int:
    now = safe_now(now)
    pref = get_preferences(db, user_id, create=False)
    if pref is None or not pref.reminders_enabled:
        cancel_user_reminders(db, user_id)
        return 0
    today = now.astimezone(ZoneInfo(pref.timezone)).date()
    # Include due dates whose furthest reminder offset falls on the next local day.
    end_day = today + timedelta(days=max(pref.reminder_offsets, default=0) + 1)
    obligations = list(db.scalars(select(Obligation).options(selectinload(Obligation.installments)).where(
        Obligation.user_id == user_id,
        Obligation.status.in_(["active", "late"]),
    )).all())
    count = 0
    for obligation in obligations:
        specs = expected_occurrences(obligation, today, end_day,
                                     include_latest_overdue=pref.overdue_enabled)
        for spec in specs:
            occurrence = materialize_occurrence(db, obligation, spec)
            if occurrence.state == "unpaid":
                count += _schedule_occurrence(db, pref, obligation, occurrence, now)
            else:
                cancel_occurrence_notifications(db, [occurrence.id])
    db.flush()
    return count
