"""Archive the legacy result tables (rename to *_archive); new tables are the only source

We move to a single source of truth: the unified pu_results / *_result_v tables. Rather
than copy data inside a migration, we simply RENAME the legacy result tables to *_archive
so the live app stops treating them as results, and a local operator script
(`pick_definitive_results.py --from-archive`) reads the *_archive tables and populates the
new tables when we are ready.

Archived (renamed) here:
  ward_results       -> ward_results_archive
  lga_party_results  -> lga_party_results_archive
  lga_results        -> lga_results_archive
  state_presidential -> state_presidential_archive

NOT archived: polling_units (still holds ward/PU geography + registered voters that the
app needs; the app just stops reading its votes_* columns — the local script reads them
to seed pu_results).

This supersedes the 0044/0045 backfill: after this runs the new *_result_v tables are
emptied of the earlier declared backfill, so they are truly empty until the script runs.

Revision ID: 0046
Revises: 0045
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ARCHIVE = ("ward_results", "lga_party_results", "lga_results", "state_presidential")


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Clear the 0044/0045 declared backfill so the new tables start empty. rolled_up
    # rows (from the picker, if any) are left untouched.
    for res_t, party_t, fk in (
        ("ward_result_v", "ward_result_parties", "ward_result_id"),
        ("lga_result_v", "lga_result_parties", "lga_result_id"),
        ("state_result_v", "state_result_parties", "state_result_id"),
        ("pu_results", "pu_result_parties", "pu_result_id"),
    ):
        if insp.has_table(res_t):
            conn.execute(sa.text(
                f"DELETE FROM {party_t} WHERE {fk} IN "
                f"(SELECT id FROM {res_t} WHERE source IN ('declared','official'))"
            ))
            conn.execute(sa.text(f"DELETE FROM {res_t} WHERE source IN ('declared','official')"))

    # Rename legacy result tables to *_archive.
    for old in _ARCHIVE:
        if insp.has_table(old) and not insp.has_table(f"{old}_archive"):
            op.rename_table(old, f"{old}_archive")


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for old in _ARCHIVE:
        if insp.has_table(f"{old}_archive") and not insp.has_table(old):
            op.rename_table(f"{old}_archive", old)
