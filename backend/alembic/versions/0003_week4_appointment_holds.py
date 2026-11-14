"""week4 appointment holds (mock write tool)

Revision ID: 0003_week4_holds
Revises: 0002_week2_profiles
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_week4_holds"
down_revision: Union[str, Sequence[str], None] = "0002_week2_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointment_holds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("appointment_holds") as b:
        b.create_index("ix_holds_user_created", ["user_id", "created_at"], unique=False)
        b.create_index("uq_active_slot_id", ["slot_id"], unique=True,
                       sqlite_where=sa.text("status = 'held'"),
                       postgresql_where=sa.text("status = 'held'"))


def downgrade() -> None:
    with op.batch_alter_table("appointment_holds") as b:
        b.drop_index("uq_active_slot_id")
        b.drop_index("ix_holds_user_created")
    op.drop_table("appointment_holds")
