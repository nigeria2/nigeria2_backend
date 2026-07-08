"""polling-unit party votes/winner + ward_results; reseed polling units

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("polling_units", sa.Column("votes_apc", sa.Integer(), nullable=True))
    op.add_column("polling_units", sa.Column("votes_lp", sa.Integer(), nullable=True))
    op.add_column("polling_units", sa.Column("votes_pdp", sa.Integer(), nullable=True))
    op.add_column("polling_units", sa.Column("votes_nnpp", sa.Integer(), nullable=True))
    op.add_column("polling_units", sa.Column("winner", sa.String(length=20), nullable=False, server_default=""))
    op.add_column("polling_units", sa.Column("runner_up", sa.String(length=20), nullable=False, server_default=""))
    # reseed polling units with the enriched data (party votes + winner)
    op.execute("DELETE FROM polling_units")

    op.create_table(
        "ward_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("lga", sa.String(length=120), nullable=False),
        sa.Column("ward", sa.String(length=160), nullable=False),
        sa.Column("ward_code", sa.String(length=30), nullable=False),
        sa.Column("votes_apc", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("votes_lp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("votes_pdp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("votes_nnpp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winner", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("runner_up", sa.String(length=20), nullable=False, server_default=""),
    )
    op.create_index("ix_ward_results_state", "ward_results", ["state"])
    op.create_index("ix_ward_results_ward_code", "ward_results", ["ward_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ward_results_ward_code", table_name="ward_results")
    op.drop_index("ix_ward_results_state", table_name="ward_results")
    op.drop_table("ward_results")
    for c in ("runner_up", "winner", "votes_nnpp", "votes_pdp", "votes_lp", "votes_apc"):
        op.drop_column("polling_units", c)
