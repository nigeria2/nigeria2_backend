"""election_sheets: link a polling unit to its INEC IReV sheet + our transcription

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("election_sheets"):
        op.create_table(
            "election_sheets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
            sa.Column("state", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("pu_code", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("sheet_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("sheet_status", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("json", sa.Text(), nullable=True),
        )
    have = {i["name"] for i in insp.get_indexes("election_sheets")} if insp.has_table("election_sheets") else set()
    for col in ("election_type", "year", "state_geo", "pu_code"):
        name = f"ix_election_sheets_{col}"
        if name not in have:
            op.create_index(name, "election_sheets", [col])


def downgrade() -> None:
    op.drop_table("election_sheets")
