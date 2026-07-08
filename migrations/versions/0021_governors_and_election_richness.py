"""add governors table + percent/running_mate on party_history

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("party_history", sa.Column("percent", sa.Float(), nullable=True))
    op.add_column("party_history", sa.Column("running_mate", sa.String(length=200), nullable=False, server_default=""))

    op.create_table(
        "governors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("party", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("party_elected", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("term_start", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("term_end", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("politician_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_governors_state", "governors", ["state"])


def downgrade() -> None:
    op.drop_index("ix_governors_state", table_name="governors")
    op.drop_table("governors")
    op.drop_column("party_history", "running_mate")
    op.drop_column("party_history", "percent")
