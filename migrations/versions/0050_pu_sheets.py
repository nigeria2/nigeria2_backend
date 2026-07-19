"""pu_sheets: one INEC sheet per (pu, office, year) + all our transcriptions of it

Stores the sheet (URL + status) and EVERY transcription we produced of it as a JSON
array (text) in `transcriptions` — the exact JSON the model returned, nothing dropped.
Flattened columns (status, legibility, model, validity_notes, discrepancies, the check
flags) surface the primary transcription's confidence + the model's own comment so the
API and filters don't have to parse the JSON.

Revision ID: 0050
Revises: 0049
Create Date: 2026-07-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _idx(table: str, cols) -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return
    have = {i["name"] for i in insp.get_indexes(table)}
    for c in cols:
        name = f"ix_{table}_{c}"
        if name not in have:
            op.create_index(name, table, [c])


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("pu_sheets"):
        op.create_table(
            "pu_sheets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pu_code", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("sheet_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("sheet_status", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("source_image", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("legibility", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("sum_check_passed", sa.Boolean(), nullable=True),
            sa.Column("totals_consistent", sa.Boolean(), nullable=True),
            sa.Column("validity_notes", sa.Text(), nullable=True),
            sa.Column("discrepancies", sa.Text(), nullable=True),
            sa.Column("transcriptions", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    _idx("pu_sheets", ("pu_code", "election_type", "year", "state_geo", "status"))


def downgrade() -> None:
    op.drop_table("pu_sheets")
