"""add wards (electoral wards with coordinates)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("lga", sa.String(length=120), nullable=False),
        sa.Column("ward", sa.String(length=160), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
    )
    op.create_index("ix_wards_state", "wards", ["state"])
    op.create_index("ix_wards_lga", "wards", ["lga"])


def downgrade() -> None:
    op.drop_index("ix_wards_lga", table_name="wards")
    op.drop_index("ix_wards_state", table_name="wards")
    op.drop_table("wards")
