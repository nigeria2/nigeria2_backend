"""legislative_results: tidy 2019 Senate + House of Reps per-candidate results

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("legislative_results"):
        op.create_table(
            "legislative_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="senate"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2019"),
            sa.Column("state", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("constituency", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("code", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("candidate", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("gender", sa.String(length=2), nullable=False, server_default=""),
            sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("elected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("politician_id", sa.Integer(), nullable=True),
        )
    have = {i["name"] for i in insp.get_indexes("legislative_results")} if insp.has_table("legislative_results") else set()
    for col in ("election_type", "year", "state", "state_geo", "constituency", "party", "politician_id"):
        name = f"ix_legislative_results_{col}"
        if name not in have:
            op.create_index(name, "legislative_results", [col])


def downgrade() -> None:
    op.drop_table("legislative_results")
