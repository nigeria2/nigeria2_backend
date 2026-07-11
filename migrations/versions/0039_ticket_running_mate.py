"""a ward prediction is for a joint ticket: add running_mate_id (VP)

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("ward_predictions"):
        cols = {c["name"] for c in insp.get_columns("ward_predictions")}
        if "running_mate_id" not in cols:
            op.add_column("ward_predictions", sa.Column("running_mate_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ward_predictions", "running_mate_id")
