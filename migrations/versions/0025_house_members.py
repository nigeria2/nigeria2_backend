"""add house_members (10th Assembly House of Reps, partial roster)

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "house_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("constituency", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("politician_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_house_members_state", "house_members", ["state"])


def downgrade() -> None:
    op.drop_index("ix_house_members_state", table_name="house_members")
    op.drop_table("house_members")
