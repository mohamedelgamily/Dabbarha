"""Short-lived, session-bound grants for audited read-only customer support."""
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FinancialSupportGrant(Base):
    __tablename__ = "admin_financial_support_grants"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'active', 'revoked', 'expired')", name="ck_support_grant_status"),
        CheckConstraint(
            "reason_code IN ('account_support', 'payment_question', 'security_review', 'data_accuracy')",
            name="ck_support_grant_reason",
        ),
        Index("ix_support_grants_target_status", "target_user_id", "status"),
        Index("ix_support_grants_requester_created", "requester_user_id", "requested_at"),
        Index("ix_support_grants_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requester_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requester_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=True
    )
    approver_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    support_case_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    self_approved: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    requested_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revoked_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
