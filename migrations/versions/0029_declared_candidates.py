"""declared candidates for future (not-yet-held) elections, e.g. 2027

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "declared_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("election_type", sa.String(length=30), nullable=False),
        sa.Column("year", sa.String(length=10), nullable=False, server_default="2027"),
        sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("politician_name", sa.String(length=200), nullable=False),
        sa.Column("politician_id", sa.Integer(), nullable=True),
        sa.Column("running_mate", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_declared_candidates_state", "declared_candidates", ["state"])
    op.create_index("ix_declared_candidates_election_type", "declared_candidates", ["election_type"])
    op.create_index("ix_declared_candidates_year", "declared_candidates", ["year"])


def downgrade() -> None:
    op.drop_index("ix_declared_candidates_year", table_name="declared_candidates")
    op.drop_index("ix_declared_candidates_election_type", table_name="declared_candidates")
    op.drop_index("ix_declared_candidates_state", table_name="declared_candidates")
    op.drop_table("declared_candidates")
