"""clear seeded opinions so the board reseeds with verified 2023 'Past Election' data

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear the illustrative opinions; startup reseeds with the verified 2023 result.
    op.execute("DELETE FROM state_predictions")


def downgrade() -> None:
    pass
