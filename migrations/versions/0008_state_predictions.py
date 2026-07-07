"""add state_predictions (shared per-state predictions board)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "state_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("author_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("election_type", sa.String(length=30), nullable=False, server_default="presidential"),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="expert"),
        sa.Column("label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("leading_party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("scores", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("year", sa.String(length=10), nullable=False, server_default="2027"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_state_predictions_user_id", "state_predictions", ["user_id"])
    op.create_index("ix_state_predictions_state", "state_predictions", ["state"])


def downgrade() -> None:
    op.drop_index("ix_state_predictions_state", table_name="state_predictions")
    op.drop_index("ix_state_predictions_user_id", table_name="state_predictions")
    op.drop_table("state_predictions")
