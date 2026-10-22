"""Administrative security audit events; never stores credentials or free-form PII."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"
    __table_args__ = (
        CheckConstraint("outcome IN ('success', 'failure')", name="ck_admin_audit_outcome"),
        Index("ix_admin_audit_actor_created", "actor_user_id", "created_at"),
        Index("ix_admin_audit_target_created", "target_user_id", "created_at"),
        Index("ix_admin_audit_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # SET NULL preserves the event while avoiding a retained link after account deletion.
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    support_grant_id: Mapped[str | None] = mapped_column(
        ForeignKey("admin_financial_support_grants.id", ondelete="SET NULL", name="fk_admin_audit_support_grant")
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    # Request source fingerprint is a one-way HMAC produced by the service; no raw IP/email.
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
