"""Add account-free notification worker heartbeat telemetry.

Revision ID: 2f2a00000001
Revises: 2f1a00000001
"""
from alembic import op
import sqlalchemy as sa

revision = "2f2a00000001"
down_revision = "2f1a00000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "worker_heartbeats",
        sa.Column("component", sa.String(length=32), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_category", sa.String(length=32), nullable=True),
        sa.Column("cycle_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_scheduled", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_deliveries", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_receipts", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("component = 'notification-worker'", name="ck_worker_heartbeat_component"),
        sa.CheckConstraint("cycle_count >= 0 AND last_scheduled >= 0 AND last_deliveries >= 0 AND last_receipts >= 0",
                           name="ck_worker_heartbeat_counts"),
    )


def downgrade():
    op.drop_table("worker_heartbeats")
