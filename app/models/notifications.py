"""Durable payment occurrences and privacy-aware push notification state."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    JSON, LargeBinary, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        CheckConstraint("reminder_time >= '00:00' AND reminder_time <= '23:59'", name="ck_notification_time"),
        CheckConstraint("language IN ('en', 'ar')", name="ck_notification_language"),
        CheckConstraint("privacy_mode IN ('detailed', 'private')", name="ck_notification_privacy"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reminder_offsets: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=lambda: [7, 3, 1, 0])
    reminder_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00", server_default="09:00")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Africa/Cairo", server_default="Africa/Cairo")
    quiet_start: Mapped[str | None] = mapped_column(String(5), nullable=True, default="22:00")
    quiet_end: Mapped[str | None] = mapped_column(String(5), nullable=True, default="07:00")
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="en", server_default="en")
    privacy_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="private", server_default="private")
    overdue_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=lambda: ["upcoming", "due_today"])
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.now())


class PushDevice(Base):
    __tablename__ = "notification_devices"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_notification_device_token_hash"),
        CheckConstraint("platform IN ('ios', 'android')", name="ck_notification_device_platform"),
        Index("ix_notification_devices_user_active", "user_id", "active"),
        Index("ix_notification_devices_session_active", "session_id", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_key_id: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(8), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.now())


class PaymentOccurrence(Base):
    __tablename__ = "payment_occurrences"
    __table_args__ = (
        UniqueConstraint("obligation_id", "occurrence_key", name="uq_payment_occurrence_key"),
        CheckConstraint("payment_kind IN ('regular', 'down_payment')", name="ck_payment_occurrence_kind"),
        CheckConstraint("state IN ('unpaid', 'paid', 'superseded')", name="ck_payment_occurrence_state"),
        CheckConstraint("scheduled_amount >= 0", name="ck_payment_occurrence_amount"),
        CheckConstraint("reminder_epoch >= 0", name="ck_payment_occurrence_epoch"),
        Index("ix_payment_occurrence_user_due_state", "user_id", "due_date", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False, index=True)
    installment_id: Mapped[int | None] = mapped_column(ForeignKey("obligation_installments.id", ondelete="SET NULL"), nullable=True)
    occurrence_key: Mapped[str] = mapped_column(String(96), nullable=False)
    payment_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    schedule_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="unpaid", server_default="unpaid")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.now())


class PaymentOccurrenceEvent(Base):
    __tablename__ = "payment_occurrence_events"
    __table_args__ = (
        CheckConstraint("action IN ('marked_paid', 'undone')", name="ck_payment_occurrence_event_action"),
        Index("ix_payment_occurrence_events_occurrence_time", "occurrence_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey("payment_occurrences.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_notification_deduplication_key"),
        CheckConstraint("notification_type IN ('upcoming', 'due_today', 'overdue', 'payment_completed')", name="ck_notification_type"),
        CheckConstraint("delivery_state IN ('queued', 'sending', 'accepted', 'platform_accepted', 'failed', 'cancelled')", name="ck_notification_delivery_state"),
        Index("ix_notifications_due_state", "delivery_state", "scheduled_at"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    obligation_id: Mapped[int | None] = mapped_column(ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True, index=True)
    occurrence_id: Mapped[int | None] = mapped_column(ForeignKey("payment_occurrences.id", ondelete="SET NULL"), nullable=True, index=True)
    notification_type: Mapped[str] = mapped_column(String(24), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(180), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(String(280), nullable=False)
    copy_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1", server_default="v1")
    route: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default="queued")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.now())


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("notification_id", "device_id", name="uq_notification_delivery_device"),
        CheckConstraint("delivery_state IN ('queued', 'sending', 'accepted', 'platform_accepted', 'failed', 'cancelled')", name="ck_notification_device_delivery_state"),
        CheckConstraint("attempt_count >= 0", name="ck_notification_delivery_attempts"),
        CheckConstraint("receipt_attempt_count >= 0", name="ck_notification_receipt_attempts"),
        Index("ix_notification_deliveries_due", "delivery_state", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("notification_devices.id", ondelete="CASCADE"), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default="queued")
    attempt_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    receipt_attempt_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    receipt_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.now())
