"""add politician aka + canonical lga table

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("politicians", sa.Column("aka", sa.Text(), nullable=False, server_default="[]"))
    op.create_table(
        "lga",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
    )
    op.create_index("ix_lga_state", "lga", ["state"])


def downgrade() -> None:
    op.drop_index("ix_lga_state", table_name="lga")
    op.drop_table("lga")
    op.drop_column("politicians", "aka")
