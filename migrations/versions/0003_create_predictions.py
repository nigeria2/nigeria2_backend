"""create predictions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("election_type", sa.String(length=20), nullable=False),
        sa.Column("party", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("measurement_week", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_predictions_state", "predictions", ["state"])
    op.create_index("ix_predictions_election_type", "predictions", ["election_type"])
    op.create_index("ix_predictions_measurement_week", "predictions", ["measurement_week"])
    op.create_index("ix_predictions_lookup", "predictions", ["election_type", "measurement_week"])


def downgrade() -> None:
    op.drop_index("ix_predictions_lookup", table_name="predictions")
    op.drop_index("ix_predictions_measurement_week", table_name="predictions")
    op.drop_index("ix_predictions_election_type", table_name="predictions")
    op.drop_index("ix_predictions_state", table_name="predictions")
    op.drop_table("predictions")
