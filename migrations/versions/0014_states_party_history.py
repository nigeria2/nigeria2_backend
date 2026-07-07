"""add states (facts + stats) and party_history

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INT_COLS = [
    "area_sq_km", "census_1991", "census_2006", "population_projection",
    "active_phone_2021", "active_phone_2020", "newly_registered_voters_2022",
    "voters_presidential_2019", "buhari_votes_2019", "atiku_votes_2019",
    "total_votes_2019", "votes_2023", "nin_total", "nin_male", "nin_female",
]


def upgrade() -> None:
    cols = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("capital", sa.String(length=80), nullable=False, server_default=""),
    ] + [sa.Column(c, sa.Integer(), nullable=True) for c in _INT_COLS]
    op.create_table("states", *cols)
    op.create_index("ix_states_name", "states", ["name"], unique=True)

    op.create_table(
        "party_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("politician_name", sa.String(length=200), nullable=False),
        sa.Column("party", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("year", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("election_type", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_party_history_politician_name", "party_history", ["politician_name"])
    op.create_index("ix_party_history_state", "party_history", ["state"])


def downgrade() -> None:
    op.drop_index("ix_party_history_state", table_name="party_history")
    op.drop_index("ix_party_history_politician_name", table_name="party_history")
    op.drop_table("party_history")
    op.drop_index("ix_states_name", table_name="states")
    op.drop_table("states")
