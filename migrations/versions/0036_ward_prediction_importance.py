"""add ward_predictions.importance (weight in the average)

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# how much weight each seeded prediction basis carries in the weighted average
_IMPORTANCE = {"Based on 2023 result": 60, "10% below 2023": 40}


def upgrade() -> None:
    conn = op.get_bind()
    if "importance" not in {c["name"] for c in sa.inspect(conn).get_columns("ward_predictions")}:
        op.add_column("ward_predictions", sa.Column("importance", sa.Integer(), nullable=False, server_default="50"))
    for label, imp in _IMPORTANCE.items():
        conn.execute(text("UPDATE ward_predictions SET importance = :i WHERE label = :l"), {"i": imp, "l": label})


def downgrade() -> None:
    op.drop_column("ward_predictions", "importance")
