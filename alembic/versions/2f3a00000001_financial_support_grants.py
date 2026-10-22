"""Add temporary, session-bound financial support grants.

Revision ID: 2f3a00000001
Revises: 2f2a00000001
"""
from alembic import op
import sqlalchemy as sa

revision = "2f3a00000001"
down_revision = "2f2a00000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_financial_support_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requester_session_id", sa.String(length=36), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("approver_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("support_case_reference", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("self_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requested_at", sa.BigInteger(), nullable=False),
        sa.Column("approved_at", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'active', 'revoked', 'expired')", name="ck_support_grant_status"),
        sa.CheckConstraint(
            "reason_code IN ('account_support', 'payment_question', 'security_review', 'data_accuracy')",
            name="ck_support_grant_reason",
        ),
    )
    op.create_index("ix_admin_financial_support_grants_target_user_id", "admin_financial_support_grants", ["target_user_id"])
    op.create_index("ix_support_grants_target_status", "admin_financial_support_grants", ["target_user_id", "status"])
    op.create_index("ix_support_grants_requester_created", "admin_financial_support_grants", ["requester_user_id", "requested_at"])
    op.create_index("ix_support_grants_expiry", "admin_financial_support_grants", ["expires_at"])
    with op.batch_alter_table("admin_audit_events") as batch:
        batch.add_column(sa.Column("support_grant_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_admin_audit_support_grant", "admin_financial_support_grants",
                                 ["support_grant_id"], ["id"], ondelete="SET NULL")


def downgrade():
    with op.batch_alter_table("admin_audit_events") as batch:
        batch.drop_constraint("fk_admin_audit_support_grant", type_="foreignkey")
        batch.drop_column("support_grant_id")
    op.drop_table("admin_financial_support_grants")
