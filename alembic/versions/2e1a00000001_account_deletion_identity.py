"""Add a PII-free SQLite user-ID high-water mark for secure hard deletion.

Revision ID: 2e1a00000001
Revises: 2d1a00000001
"""
from alembic import op
import sqlalchemy as sa

revision = "2e1a00000001"
down_revision = "2d1a00000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_id_sequence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_account_id_sequence_singleton"),
    )
    # This singleton contains only a global high-water mark, never an account ID
    # history or user identifier. SQLite can otherwise reuse a deleted max rowid,
    # allowing an unexpired legacy JWT subject to match a later account.
    op.execute(sa.text(
        "INSERT INTO account_id_sequence (id, last_id) "
        "SELECT 1, COALESCE(MAX(id), 0) FROM users"
    ))


def downgrade():
    op.drop_table("account_id_sequence")
