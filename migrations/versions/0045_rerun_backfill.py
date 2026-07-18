"""Re-run the results backfill (idempotent)

0044 backfills legacy results into the *_result_v tables. On environments where the
0043/0044 tables were created out-of-band (e.g. via create_all after a swallowed
migration error) the alembic version can sit past 0044 while the *_result_v tables are
empty. This revision simply re-runs 0044's idempotent backfill so the declared rows are
present regardless of how the tables came to exist. Safe to run repeatedly (it clears
its own source='declared' rows first).

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-18

"""
from typing import Sequence, Union

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reuse 0044's idempotent backfill verbatim.
    import importlib
    mod = importlib.import_module("migrations.versions.0044_backfill_results")
    mod.upgrade()


def downgrade() -> None:
    pass
