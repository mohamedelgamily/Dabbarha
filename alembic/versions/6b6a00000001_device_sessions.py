"""Add durable device sessions, encrypted retry receipts and legacy revocation.

Revision ID: 6b6a00000001
Revises: 17d4d0e39961
"""
from alembic import op
import sqlalchemy as sa

revision = "6b6a00000001"
down_revision = "17d4d0e39961"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_label", sa.String(80)),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("last_refreshed_at", sa.BigInteger(), nullable=False),
        sa.Column("idle_expires_at", sa.BigInteger(), nullable=False),
        sa.Column("absolute_expires_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger()),
        sa.Column("revocation_reason", sa.String(32)),
        sa.Column("current_refresh_hash", sa.String(64), nullable=False),
        sa.Column("current_generation", sa.Integer(), nullable=False),
        sa.CheckConstraint("current_generation >= 0", name="ck_session_generation"),
        sa.CheckConstraint("created_at <= idle_expires_at AND idle_expires_at <= absolute_expires_at", name="ck_session_expiry"))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_absolute_expires_at", "auth_sessions", ["absolute_expires_at"])
    op.create_table("auth_refresh_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("consumed_at", sa.BigInteger()),
        sa.Column("retry_key_hash", sa.String(64)),
        sa.Column("successor_token_hash", sa.String(64)),
        sa.Column("recovery_expires_at", sa.BigInteger()),
        sa.Column("recovery_count", sa.Integer(), nullable=False),
        sa.Column("response_ciphertext", sa.LargeBinary()),
        sa.Column("encryption_nonce", sa.LargeBinary()),
        sa.Column("encryption_key_id", sa.String(32)),
        sa.UniqueConstraint("session_id", "generation", name="uq_refresh_generation"),
        sa.CheckConstraint("generation >= 0 AND recovery_count >= 0 AND recovery_count <= 2", name="ck_refresh_counts"),
        sa.CheckConstraint("issued_at <= expires_at", name="ck_refresh_expiry"))
    op.create_index("ix_auth_refresh_tokens_session_id", "auth_refresh_tokens", ["session_id"])
    op.create_index("ix_auth_refresh_tokens_recovery_expires_at", "auth_refresh_tokens", ["recovery_expires_at"])
    op.create_table("legacy_access_revocations",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False))
    op.create_index("ix_legacy_access_revocations_user_id", "legacy_access_revocations", ["user_id"])
    op.create_index("ix_legacy_access_revocations_expires_at", "legacy_access_revocations", ["expires_at"])


def downgrade():
    # Explicit destructive downgrade, never run automatically; destroys session history.
    op.drop_table("legacy_access_revocations")
    op.drop_table("auth_refresh_tokens")
    op.drop_table("auth_sessions")
