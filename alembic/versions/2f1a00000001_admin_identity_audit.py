"""Add default-off admin identity fields and security audit trail.

Revision ID: 2f1a00000001
Revises: 2e1a00000001
"""
from alembic import op
import sqlalchemy as sa

revision = "2f1a00000001"
down_revision = "2e1a00000001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("admin_role", sa.String(length=16), server_default="user", nullable=False))
        batch.add_column(sa.Column("admin_totp_nonce", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("admin_totp_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("admin_totp_key_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("admin_totp_last_step", sa.BigInteger(), nullable=True))
        batch.create_check_constraint("ck_users_admin_role", "admin_role IN ('user', 'admin', 'superadmin')")
    op.create_table("admin_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("outcome IN ('success', 'failure')", name="ck_admin_audit_outcome"),
    )
    op.create_index("ix_admin_audit_actor_created", "admin_audit_events", ["actor_user_id", "created_at"])
    op.create_index("ix_admin_audit_target_created", "admin_audit_events", ["target_user_id", "created_at"])
    op.create_index("ix_admin_audit_created", "admin_audit_events", ["created_at"])


def downgrade():
    op.drop_table("admin_audit_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_admin_role", type_="check")
        batch.drop_column("admin_totp_last_step")
        batch.drop_column("admin_totp_key_id")
        batch.drop_column("admin_totp_ciphertext")
        batch.drop_column("admin_totp_nonce")
        batch.drop_column("admin_role")
