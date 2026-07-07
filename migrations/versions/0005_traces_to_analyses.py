"""replace traces with analyses (per-party scores)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("traces")  # seed-only; superseded by richer analyses
    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("contributor_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("contributor_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("election_type", sa.String(length=30), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("lga", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("senatorial_district", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("leading_party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("scores", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("measurement_week", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_analyses_user_id", "analyses", ["user_id"])
    op.create_index("ix_analyses_state", "analyses", ["state"])
    op.create_index("ix_analyses_measurement_week", "analyses", ["measurement_week"])


def downgrade() -> None:
    op.drop_index("ix_analyses_measurement_week", table_name="analyses")
    op.drop_index("ix_analyses_state", table_name="analyses")
    op.drop_index("ix_analyses_user_id", table_name="analyses")
    op.drop_table("analyses")
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
