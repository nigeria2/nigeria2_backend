"""lga_party_results: tidy per-LGA per-party 2023 results (presidential + governor)

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("lga_party_results"):
        op.create_table(
            "lga_party_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
            sa.Column("state", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("lga_id", sa.Integer(), nullable=True),
            sa.Column("lga", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        )
    have = {i["name"] for i in insp.get_indexes("lga_party_results")} if insp.has_table("lga_party_results") else set()
    for col in ("election_type", "year", "state", "state_geo", "lga_id", "party"):
        name = f"ix_lga_party_results_{col}"
        if name not in have:
            op.create_index(name, "lga_party_results", [col])


def downgrade() -> None:
    op.drop_table("lga_party_results")
