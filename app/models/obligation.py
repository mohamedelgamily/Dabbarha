from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Obligation(Base):
    __tablename__ = "obligations"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_obligations_total_amount_non_negative"),
        CheckConstraint(
            "monthly_installment_amount >= 0",
            name="ck_obligations_monthly_installment_amount_non_negative",
        ),
        CheckConstraint("term_months > 0", name="ck_obligations_term_months_positive"),
        CheckConstraint(
            "due_day_of_month >= 1 AND due_day_of_month <= 31",
            name="ck_obligations_due_day_of_month_range",
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'late', 'defaulted')",
            name="ck_obligations_status_allowed",
        ),
        CheckConstraint(
            "source IN ('manual_entry', 'chatbot_entry')",
            name="ck_obligations_source_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monthly_installment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int] = mapped_column(nullable=False)
    due_day_of_month: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual_entry",
        server_default="manual_entry",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="obligations")
