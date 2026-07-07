"""link party_history to politicians; reseed with links + governor politicians

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("party_history", sa.Column("politician_id", sa.Integer(), nullable=True))
    op.create_index("ix_party_history_politician_id", "party_history", ["politician_id"])
    # Reseed so governor candidates become politicians and get linked.
    op.execute("DELETE FROM party_history")


def downgrade() -> None:
    op.drop_index("ix_party_history_politician_id", table_name="party_history")
    op.drop_column("party_history", "politician_id")
