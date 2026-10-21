"""Non-user-linked high-water mark to prevent SQLite account ID reuse."""
from sqlalchemy import BigInteger, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AccountIdSequence(Base):
    __tablename__ = "account_id_sequence"
    __table_args__ = (CheckConstraint("id = 1", name="ck_account_id_sequence_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    last_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
