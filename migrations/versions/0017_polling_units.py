"""add polling_units

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "polling_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("lga", sa.String(length=120), nullable=False),
        sa.Column("ward", sa.String(length=160), nullable=False),
        sa.Column("ward_code", sa.String(length=30), nullable=False),
        sa.Column("pu_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("pu_code", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("registered_voters", sa.Integer(), nullable=True),
        sa.Column("known_votes", sa.Integer(), nullable=True),
    )
    op.create_index("ix_polling_units_state", "polling_units", ["state"])
    op.create_index("ix_polling_units_ward_code", "polling_units", ["ward_code"])


def downgrade() -> None:
    op.drop_index("ix_polling_units_ward_code", table_name="polling_units")
    op.drop_index("ix_polling_units_state", table_name="polling_units")
    op.drop_table("polling_units")
