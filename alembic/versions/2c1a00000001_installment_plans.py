"""Add opt-in installment plan metadata and exact scheduled installments.

Revision ID: 2c1a00000001
Revises: 6b6a00000001
"""
from alembic import op
import sqlalchemy as sa

revision = "2c1a00000001"
down_revision = "6b6a00000001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("obligations") as batch:
        batch.add_column(sa.Column("purchase_price", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("payment_method", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("interest_method", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("nominal_annual_interest_rate", sa.Numeric(7, 4), nullable=True))
        batch.add_column(sa.Column("down_payment_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"))
        batch.add_column(sa.Column("down_payment_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("down_payment_paid", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("schedule_version", sa.Integer(), nullable=False, server_default="0"))
        batch.create_check_constraint(
            "ck_obligations_payment_method",
            "payment_method IS NULL OR payment_method IN ('manual', 'automatic')",
        )
        batch.create_check_constraint(
            "ck_obligations_interest_method",
            "interest_method IS NULL OR interest_method IN ('none', 'flat', 'reducing_balance')",
        )
        batch.create_check_constraint(
            "ck_obligations_interest_rate_range",
            "nominal_annual_interest_rate IS NULL OR "
            "(nominal_annual_interest_rate >= 0 AND nominal_annual_interest_rate <= 100)",
        )
        batch.create_check_constraint("ck_obligations_down_payment_non_negative", "down_payment_amount >= 0")
        batch.create_check_constraint(
            "ck_obligations_down_payment_state",
            "(down_payment_amount = 0 AND down_payment_date IS NULL AND down_payment_paid = false) OR "
            "(down_payment_amount > 0 AND down_payment_date IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_obligations_down_payment_below_purchase_price",
            "purchase_price IS NULL OR down_payment_amount < purchase_price",
        )
        batch.create_check_constraint("ck_obligations_schedule_version", "schedule_version >= 0")

    op.create_table(
        "obligation_installments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("obligation_id", sa.Integer(), sa.ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("installment_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("scheduled_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("principal_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("interest_amount", sa.Numeric(12, 2), nullable=True),
        sa.UniqueConstraint("obligation_id", "installment_number", name="uq_installment_number_per_obligation"),
        sa.CheckConstraint(
            "installment_number >= 1 AND installment_number <= 1200", name="ck_installment_number_range"
        ),
        sa.CheckConstraint("scheduled_amount >= 0", name="ck_installment_amount_non_negative"),
        sa.CheckConstraint(
            "principal_amount IS NULL OR principal_amount >= 0", name="ck_installment_principal_non_negative"
        ),
        sa.CheckConstraint("interest_amount IS NULL OR interest_amount >= 0", name="ck_installment_interest_non_negative"),
    )
    op.create_index("ix_obligation_installments_obligation_id", "obligation_installments", ["obligation_id"])


def downgrade():
    # This removes opted-in plan data. Downgrade is intended for disposable databases only.
    op.drop_index("ix_obligation_installments_obligation_id", table_name="obligation_installments")
    op.drop_table("obligation_installments")
    with op.batch_alter_table("obligations") as batch:
        batch.drop_constraint("ck_obligations_schedule_version", type_="check")
        batch.drop_constraint("ck_obligations_down_payment_below_purchase_price", type_="check")
        batch.drop_constraint("ck_obligations_down_payment_state", type_="check")
        batch.drop_constraint("ck_obligations_down_payment_non_negative", type_="check")
        batch.drop_constraint("ck_obligations_interest_rate_range", type_="check")
        batch.drop_constraint("ck_obligations_interest_method", type_="check")
        batch.drop_constraint("ck_obligations_payment_method", type_="check")
        batch.drop_column("schedule_version")
        batch.drop_column("down_payment_paid")
        batch.drop_column("down_payment_date")
        batch.drop_column("down_payment_amount")
        batch.drop_column("nominal_annual_interest_rate")
        batch.drop_column("interest_method")
        batch.drop_column("payment_method")
        batch.drop_column("purchase_price")
