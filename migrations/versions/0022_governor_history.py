"""add governor_history (past governors since 2007)

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "governor_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("party", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("term_start", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("term_end", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("acting", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("politician_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_governor_history_state", "governor_history", ["state"])


def downgrade() -> None:
    op.drop_index("ix_governor_history_state", table_name="governor_history")
    op.drop_table("governor_history")
