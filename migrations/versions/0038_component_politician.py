"""link a prediction component to a politician (candidate / running mate)

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("prediction_components"):
        cols = {c["name"] for c in insp.get_columns("prediction_components")}
        if "politician_id" not in cols:
            op.add_column("prediction_components", sa.Column("politician_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("prediction_components", "politician_id")
