"""politician photos + assessments, and photo column on politicians

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("politicians", sa.Column("photo", sa.Text(), nullable=False, server_default=""))

    op.create_table(
        "politician_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("politician_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("image", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_politician_photos_politician_id", "politician_photos", ["politician_id"])
    op.create_index("ix_politician_photos_status", "politician_photos", ["status"])

    op.create_table(
        "politician_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("politician_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("electoral_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("influential_lgas", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_politician_assessments_politician_id", "politician_assessments", ["politician_id"])


def downgrade() -> None:
    op.drop_index("ix_politician_assessments_politician_id", table_name="politician_assessments")
    op.drop_table("politician_assessments")
    op.drop_index("ix_politician_photos_status", table_name="politician_photos")
    op.drop_index("ix_politician_photos_politician_id", table_name="politician_photos")
    op.drop_table("politician_photos")
    op.drop_column("politicians", "photo")
