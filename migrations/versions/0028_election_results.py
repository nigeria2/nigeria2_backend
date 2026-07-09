"""historical election results (1999-2022 gov & presidential)

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "election_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("office", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("scores", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("registered_voters", sa.Integer(), nullable=True),
        sa.Column("total_votes", sa.Integer(), nullable=True),
        sa.Column("winner_party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("winner_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=40), nullable=False, server_default=""),
    )
    op.create_index("ix_election_results_year", "election_results", ["year"])
    op.create_index("ix_election_results_office", "election_results", ["office"])
    op.create_index("ix_election_results_state", "election_results", ["state"])
    op.create_index("ix_election_results_winner_party", "election_results", ["winner_party"])


def downgrade() -> None:
    op.drop_index("ix_election_results_winner_party", table_name="election_results")
    op.drop_index("ix_election_results_state", table_name="election_results")
    op.drop_index("ix_election_results_office", table_name="election_results")
    op.drop_index("ix_election_results_year", table_name="election_results")
    op.drop_table("election_results")
