"""add state_presidential (2023 presidential by state)

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "state_presidential",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False, server_default="2023"),
        sa.Column("apc", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pdp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nnpp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("others", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("turnout", sa.Float(), nullable=True),
        sa.Column("winner", sa.String(length=20), nullable=False, server_default=""),
    )
    op.create_index("ix_state_presidential_state", "state_presidential", ["state"])


def downgrade() -> None:
    op.drop_index("ix_state_presidential_state", table_name="state_presidential")
    op.drop_table("state_presidential")
