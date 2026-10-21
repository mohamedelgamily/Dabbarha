"""Add durable occurrences, preferences, device registration and notifications.

Revision ID: 2d1a00000001
Revises: 2c1a00000001
"""
from alembic import op
import sqlalchemy as sa

revision = "2d1a00000001"
down_revision = "2c1a00000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminder_offsets", sa.JSON(), nullable=False, server_default=sa.text("'[7,3,1,0]'")),
        sa.Column("reminder_time", sa.String(5), nullable=False, server_default="09:00"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Africa/Cairo"),
        sa.Column("quiet_start", sa.String(5), nullable=True, server_default="22:00"),
        sa.Column("quiet_end", sa.String(5), nullable=True, server_default="07:00"),
        sa.Column("language", sa.String(2), nullable=False, server_default="en"),
        sa.Column("privacy_mode", sa.String(12), nullable=False, server_default="private"),
        sa.Column("overdue_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("categories", sa.JSON(), nullable=False, server_default=sa.text("'[\"upcoming\",\"due_today\"]'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("reminder_time >= '00:00' AND reminder_time <= '23:59'", name="ck_notification_time"),
        sa.CheckConstraint("language IN ('en', 'ar')", name="ck_notification_language"),
        sa.CheckConstraint("privacy_mode IN ('detailed', 'private')", name="ck_notification_privacy"),
    )

    op.create_table(
        "notification_devices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("token_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("token_key_id", sa.String(32), nullable=False),
        sa.Column("platform", sa.String(8), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_notification_device_token_hash"),
        sa.CheckConstraint("platform IN ('ios', 'android')", name="ck_notification_device_platform"),
    )
    op.create_index("ix_notification_devices_user_id", "notification_devices", ["user_id"])
    op.create_index("ix_notification_devices_user_active", "notification_devices", ["user_id", "active"])
    op.create_index("ix_notification_devices_session_active", "notification_devices", ["session_id", "active"])

    op.create_table(
        "payment_occurrences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("obligation_id", sa.Integer(), sa.ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("installment_id", sa.Integer(), sa.ForeignKey("obligation_installments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurrence_key", sa.String(96), nullable=False),
        sa.Column("payment_kind", sa.String(20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("scheduled_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("schedule_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(12), nullable=False, server_default="unpaid"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_epoch", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("obligation_id", "occurrence_key", name="uq_payment_occurrence_key"),
        sa.CheckConstraint("payment_kind IN ('regular', 'down_payment')", name="ck_payment_occurrence_kind"),
        sa.CheckConstraint("state IN ('unpaid', 'paid', 'superseded')", name="ck_payment_occurrence_state"),
        sa.CheckConstraint("scheduled_amount >= 0", name="ck_payment_occurrence_amount"),
        sa.CheckConstraint("reminder_epoch >= 0", name="ck_payment_occurrence_epoch"),
    )
    op.create_index("ix_payment_occurrences_user_id", "payment_occurrences", ["user_id"])
    op.create_index("ix_payment_occurrences_obligation_id", "payment_occurrences", ["obligation_id"])
    op.create_index("ix_payment_occurrence_user_due_state", "payment_occurrences", ["user_id", "due_date", "state"])

    op.create_table(
        "payment_occurrence_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("payment_occurrences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("action IN ('marked_paid', 'undone')", name="ck_payment_occurrence_event_action"),
    )
    op.create_index("ix_payment_occurrence_events_occurrence_id", "payment_occurrence_events", ["occurrence_id"])
    op.create_index("ix_payment_occurrence_events_user_id", "payment_occurrence_events", ["user_id"])
    op.create_index("ix_payment_occurrence_events_occurrence_time", "payment_occurrence_events", ["occurrence_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("obligation_id", sa.Integer(), sa.ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("payment_occurrences.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notification_type", sa.String(24), nullable=False),
        sa.Column("deduplication_key", sa.String(180), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("body", sa.String(280), nullable=False),
        sa.Column("copy_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("route", sa.String(100), nullable=True),
        sa.Column("delivery_state", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("deduplication_key", name="uq_notification_deduplication_key"),
        sa.CheckConstraint("notification_type IN ('upcoming', 'due_today', 'overdue', 'payment_completed')", name="ck_notification_type"),
        sa.CheckConstraint("delivery_state IN ('queued', 'sending', 'accepted', 'platform_accepted', 'failed', 'cancelled')", name="ck_notification_delivery_state"),
    )
    for name, columns in (
        ("ix_notifications_user_id", ["user_id"]),
        ("ix_notifications_obligation_id", ["obligation_id"]),
        ("ix_notifications_occurrence_id", ["occurrence_id"]),
        ("ix_notifications_scheduled_at", ["scheduled_at"]),
        ("ix_notifications_due_state", ["delivery_state", "scheduled_at"]),
        ("ix_notifications_user_created", ["user_id", "created_at"]),
    ):
        op.create_index(name, "notifications", columns)

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("notification_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivery_state", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("receipt_attempt_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("receipt_status", sa.String(32), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("notification_id", "device_id", name="uq_notification_delivery_device"),
        sa.CheckConstraint("delivery_state IN ('queued', 'sending', 'accepted', 'platform_accepted', 'failed', 'cancelled')", name="ck_notification_device_delivery_state"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_notification_delivery_attempts"),
        sa.CheckConstraint("receipt_attempt_count >= 0", name="ck_notification_receipt_attempts"),
    )
    op.create_index("ix_notification_deliveries_next_attempt_at", "notification_deliveries", ["next_attempt_at"])
    op.create_index("ix_notification_deliveries_lease_until", "notification_deliveries", ["lease_until"])
    op.create_index("ix_notification_deliveries_due", "notification_deliveries", ["delivery_state", "next_attempt_at"])


def downgrade():
    op.drop_table("notification_deliveries")
    for name in ("ix_notifications_user_created", "ix_notifications_due_state", "ix_notifications_scheduled_at",
                 "ix_notifications_occurrence_id", "ix_notifications_obligation_id", "ix_notifications_user_id"):
        op.drop_index(name, table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_payment_occurrence_events_occurrence_time", table_name="payment_occurrence_events")
    op.drop_index("ix_payment_occurrence_events_user_id", table_name="payment_occurrence_events")
    op.drop_index("ix_payment_occurrence_events_occurrence_id", table_name="payment_occurrence_events")
    op.drop_table("payment_occurrence_events")
    op.drop_index("ix_payment_occurrence_user_due_state", table_name="payment_occurrences")
    op.drop_index("ix_payment_occurrences_obligation_id", table_name="payment_occurrences")
    op.drop_index("ix_payment_occurrences_user_id", table_name="payment_occurrences")
    op.drop_table("payment_occurrences")
    op.drop_index("ix_notification_devices_session_active", table_name="notification_devices")
    op.drop_index("ix_notification_devices_user_active", table_name="notification_devices")
    op.drop_index("ix_notification_devices_user_id", table_name="notification_devices")
    op.drop_table("notification_devices")
    op.drop_table("notification_preferences")
