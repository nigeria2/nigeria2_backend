"""add ward_predictions table (per-ward vote projections)

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("ward_predictions"):
        op.create_table(
            "ward_predictions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("election_type", sa.String(length=30), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2027"),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("lga_id", sa.Integer(), nullable=False),
            sa.Column("ward_code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("politician_id", sa.Integer(), nullable=True),
            sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("label", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    have = {i["name"] for i in insp.get_indexes("ward_predictions")} if insp.has_table("ward_predictions") else set()
    for col in ("election_type", "year", "state_geo", "lga_id", "ward_code"):
        name = f"ix_ward_predictions_{col}"
        if name not in have:
            op.create_index(name, "ward_predictions", [col])


def downgrade() -> None:
    op.drop_table("ward_predictions")
