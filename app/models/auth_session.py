"""Durable credentials use hashes and encrypted receipts, never plaintext tokens.

Times are UTC Unix seconds (BIGINT) on both SQLite and PostgreSQL.
"""
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("current_generation >= 0", name="ck_session_generation"),
        CheckConstraint("created_at <= idle_expires_at AND idle_expires_at <= absolute_expires_at", name="ck_session_expiry"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_label: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[int] = mapped_column(BigInteger)
    last_refreshed_at: Mapped[int] = mapped_column(BigInteger)
    idle_expires_at: Mapped[int] = mapped_column(BigInteger)
    absolute_expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
    revoked_at: Mapped[int | None] = mapped_column(BigInteger)
    revocation_reason: Mapped[str | None] = mapped_column(String(32))
    current_refresh_hash: Mapped[str] = mapped_column(String(64))
    current_generation: Mapped[int] = mapped_column(Integer)


class AuthRefreshToken(Base):
    __tablename__ = "auth_refresh_tokens"
    __table_args__ = (
        UniqueConstraint("session_id", "generation", name="uq_refresh_generation"),
        CheckConstraint("generation >= 0 AND recovery_count >= 0 AND recovery_count <= 2", name="ck_refresh_counts"),
        CheckConstraint("issued_at <= expires_at", name="ck_refresh_expiry"),
    )
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[int] = mapped_column(BigInteger)
    consumed_at: Mapped[int | None] = mapped_column(BigInteger)
    retry_key_hash: Mapped[str | None] = mapped_column(String(64))
    successor_token_hash: Mapped[str | None] = mapped_column(String(64))
    recovery_expires_at: Mapped[int | None] = mapped_column(BigInteger, index=True)
    recovery_count: Mapped[int] = mapped_column(Integer, default=0)
    response_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_key_id: Mapped[str | None] = mapped_column(String(32))


class LegacyAccessRevocation(Base):
    __tablename__ = "legacy_access_revocations"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    revoked_at: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
