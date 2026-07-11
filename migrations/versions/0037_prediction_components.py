"""add prediction_components table (a prediction is the sum of its components)

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("prediction_components"):
        op.create_table(
            "prediction_components",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ward_prediction_id", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        )
    have = {i["name"] for i in insp.get_indexes("prediction_components")} if insp.has_table("prediction_components") else set()
    if "ix_prediction_components_ward_prediction_id" not in have:
        op.create_index("ix_prediction_components_ward_prediction_id", "prediction_components", ["ward_prediction_id"])


def downgrade() -> None:
    op.drop_table("prediction_components")
