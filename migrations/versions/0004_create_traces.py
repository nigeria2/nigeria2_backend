"""create traces table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("contributor_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("contributor_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("lga", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("election_type", sa.String(length=30), nullable=False),
        sa.Column("party", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("measurement_week", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_traces_user_id", "traces", ["user_id"])
    op.create_index("ix_traces_state", "traces", ["state"])
    op.create_index("ix_traces_measurement_week", "traces", ["measurement_week"])


def downgrade() -> None:
    op.drop_index("ix_traces_measurement_week", table_name="traces")
    op.drop_index("ix_traces_state", table_name="traces")
    op.drop_index("ix_traces_user_id", table_name="traces")
    op.drop_table("traces")
