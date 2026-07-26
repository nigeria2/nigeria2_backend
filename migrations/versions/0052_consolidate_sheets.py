"""Consolidate result sheets into pu_sheets; drop legacy election_sheets.

There were two sheet tables. `election_sheets` (~17k rows) only ever covered Akwa
Ibom + Adamawa and used the spellings governorship/senatorial; the per-PU page read
ONLY from it, so sheets never showed for the other 35 states. `pu_sheets` (~351k
rows) holds the real, current sheet + transcription data for all 37 states using
governor/senate. This migration folds any election_sheets row not already present in
pu_sheets into pu_sheets (normalising the election_type), then drops election_sheets.

The API now reads sheets from pu_sheets only.

Revision ID: 0052
Revises: 0051
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("election_sheets"):
        return  # already consolidated

    if insp.has_table("pu_sheets"):
        # Migrate every election_sheets row whose (pu_code, normalized type, year) is not
        # already in pu_sheets. Preserve the legacy transcription JSON and status so no
        # provenance is lost — including 'no_sheet' rows that record INEC had no sheet.
        bind.execute(sa.text("""
            INSERT INTO pu_sheets
                (pu_code, election_type, year, state_geo, sheet_url, sheet_status,
                 source_image, status, legibility, model,
                 sum_check_passed, totals_consistent, validity_notes, discrepancies,
                 transcriptions)
            SELECT es.pu_code,
                   CASE es.election_type
                       WHEN 'governorship' THEN 'governor'
                       WHEN 'senatorial'   THEN 'senate'
                       ELSE es.election_type END,
                   es.year, es.state_geo,
                   COALESCE(es.sheet_url, ''), COALESCE(es.sheet_status, ''),
                   '', '', '', '',
                   NULL, NULL, NULL, NULL,
                   es.json
            FROM election_sheets es
            WHERE NOT EXISTS (
                SELECT 1 FROM pu_sheets ps
                WHERE ps.pu_code = es.pu_code
                  AND ps.election_type = CASE es.election_type
                       WHEN 'governorship' THEN 'governor'
                       WHEN 'senatorial'   THEN 'senate'
                       ELSE es.election_type END
                  AND ps.year = es.year
            )
        """))

    op.drop_table("election_sheets")


def downgrade() -> None:
    # Recreate the (now empty) legacy table shell so a downgrade doesn't crash. The
    # migrated data stays in pu_sheets; we do not attempt to split it back out.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("election_sheets"):
        return
    op.create_table(
        "election_sheets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("election_type", sa.String(length=20), nullable=False),
        sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
        sa.Column("state", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("state_geo", sa.String(length=20), nullable=True),
        sa.Column("pu_code", sa.String(length=40), nullable=False),
        sa.Column("sheet_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("sheet_status", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("json", sa.Text(), nullable=True),
    )
    op.create_index("ix_election_sheets_election_type", "election_sheets", ["election_type"])
    op.create_index("ix_election_sheets_year", "election_sheets", ["year"])
    op.create_index("ix_election_sheets_state_geo", "election_sheets", ["state_geo"])
    op.create_index("ix_election_sheets_pu_code", "election_sheets", ["pu_code"])
