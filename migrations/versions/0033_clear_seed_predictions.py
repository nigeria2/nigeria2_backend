"""clear illustrative seed predictions + analyses

These two tables were seeded with illustrative/synthetic rows (fake contributors,
pseudo-random scores). They are now emptied so the site only ever shows real data;
the seed calls have been removed so they are not repopulated.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM predictions"))
    conn.execute(text("DELETE FROM analyses"))


def downgrade() -> None:
    # illustrative seed data is intentionally not restored
    pass
