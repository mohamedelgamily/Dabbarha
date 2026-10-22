"""Account-free operational heartbeat for the notification worker."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    __table_args__ = (
        CheckConstraint("component = 'notification-worker'", name="ck_worker_heartbeat_component"),
        CheckConstraint("cycle_count >= 0 AND last_scheduled >= 0 AND last_deliveries >= 0 AND last_receipts >= 0",
                        name="ck_worker_heartbeat_counts"),
    )

    component: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_category: Mapped[str | None] = mapped_column(String(32))
    cycle_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    last_scheduled: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    last_deliveries: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    last_receipts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
