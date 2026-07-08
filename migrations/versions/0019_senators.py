"""add senators (10th National Assembly)

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "senators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("district", sa.String(length=60), nullable=False),
        sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("gender", sa.String(length=12), nullable=False, server_default=""),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("terms", sa.Integer(), nullable=True),
        sa.Column("leadership", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("politician_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_senators_state", "senators", ["state"])


def downgrade() -> None:
    op.drop_index("ix_senators_state", table_name="senators")
    op.drop_table("senators")
