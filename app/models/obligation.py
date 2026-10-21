from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, false, func
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
        CheckConstraint(
            "payment_method IS NULL OR payment_method IN ('manual', 'automatic')",
            name="ck_obligations_payment_method",
        ),
        CheckConstraint(
            "interest_method IS NULL OR interest_method IN ('none', 'flat', 'reducing_balance')",
            name="ck_obligations_interest_method",
        ),
        CheckConstraint(
            "nominal_annual_interest_rate IS NULL OR "
            "(nominal_annual_interest_rate >= 0 AND nominal_annual_interest_rate <= 100)",
            name="ck_obligations_interest_rate_range",
        ),
        CheckConstraint("down_payment_amount >= 0", name="ck_obligations_down_payment_non_negative"),
        CheckConstraint(
            "(down_payment_amount = 0 AND down_payment_date IS NULL AND down_payment_paid = false) OR "
            "(down_payment_amount > 0 AND down_payment_date IS NOT NULL)",
            name="ck_obligations_down_payment_state",
        ),
        CheckConstraint("schedule_version >= 0", name="ck_obligations_schedule_version"),
        CheckConstraint(
            "purchase_price IS NULL OR down_payment_amount < purchase_price",
            name="ck_obligations_down_payment_below_purchase_price",
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
    # Null fields retain the original legacy calculation path.
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    interest_method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    nominal_annual_interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    down_payment_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    down_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    down_payment_paid: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=false())
    schedule_version: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
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
    installments: Mapped[list["ObligationInstallment"]] = relationship(
        back_populates="obligation", cascade="all, delete-orphan", order_by="ObligationInstallment.installment_number"
    )


class ObligationInstallment(Base):
    __tablename__ = "obligation_installments"
    __table_args__ = (
        UniqueConstraint("obligation_id", "installment_number", name="uq_installment_number_per_obligation"),
        CheckConstraint("installment_number >= 1 AND installment_number <= 1200", name="ck_installment_number_range"),
        CheckConstraint("scheduled_amount >= 0", name="ck_installment_amount_non_negative"),
        CheckConstraint("principal_amount IS NULL OR principal_amount >= 0", name="ck_installment_principal_non_negative"),
        CheckConstraint("interest_amount IS NULL OR interest_amount >= 0", name="ck_installment_interest_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installment_number: Mapped[int] = mapped_column(nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    principal_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    interest_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    obligation: Mapped[Obligation] = relationship(back_populates="installments")
