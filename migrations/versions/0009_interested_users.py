"""rename signups -> interested_users

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("signups", "interested_users")


def downgrade() -> None:
    op.rename_table("interested_users", "signups")
