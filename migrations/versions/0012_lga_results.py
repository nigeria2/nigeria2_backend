"""add lga_results (per-LGA 2023 presidential results)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lga_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("lga", sa.String(length=120), nullable=False),
        sa.Column("leading_party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("scores", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("total_votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lga_results_state", "lga_results", ["state"])


def downgrade() -> None:
    op.drop_index("ix_lga_results_state", table_name="lga_results")
    op.drop_table("lga_results")
