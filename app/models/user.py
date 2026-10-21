from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, LargeBinary, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.obligation import Obligation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("monthly_income >= 0", name="ck_users_monthly_income_non_negative"),
        CheckConstraint("fixed_expenses >= 0", name="ck_users_fixed_expenses_non_negative"),
        CheckConstraint("admin_role IN ('user', 'admin', 'superadmin')", name="ck_users_admin_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    fixed_expenses: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EGP",
        server_default="EGP",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    # Admin access is default-off for every existing and newly registered account.
    admin_role: Mapped[str] = mapped_column(String(16), nullable=False, default="user", server_default="user")
    admin_totp_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    admin_totp_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    admin_totp_key_id: Mapped[str | None] = mapped_column(String(32))
    admin_totp_last_step: Mapped[int | None] = mapped_column(BigInteger)

    obligations: Mapped[list["Obligation"]] = relationship(
        back_populates="user",
    )
