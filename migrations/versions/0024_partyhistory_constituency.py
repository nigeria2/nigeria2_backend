"""add party_history.constituency (senate district etc.)

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("party_history", sa.Column("constituency", sa.String(length=80), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("party_history", "constituency")
