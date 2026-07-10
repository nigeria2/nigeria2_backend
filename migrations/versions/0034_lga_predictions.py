"""add lga_predictions table (per-LGA vote predictions)

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    # Idempotent: the table may already have been created out-of-band.
    if not insp.has_table("lga_predictions"):
        op.create_table(
            "lga_predictions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("election_type", sa.String(length=30), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2027"),
            sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("lga_id", sa.Integer(), nullable=False),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("politician_id", sa.Integer(), nullable=True),
            sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    have = {i["name"] for i in insp.get_indexes("lga_predictions")} if insp.has_table("lga_predictions") else set()
    for col in ("election_type", "year", "lga_id", "state_geo"):
        name = f"ix_lga_predictions_{col}"
        if name not in have:
            op.create_index(name, "lga_predictions", [col])


def downgrade() -> None:
    op.drop_table("lga_predictions")
