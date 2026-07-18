"""No 'definitive' / 'chosen' — every entry is a guess; result is a merge

Corrections to the model:
- We are never sure of any data; there is no single chosen evidence and no "definitive".
  The polling-unit result is a MERGE of the evidence (today: a copy of the one entry).
- Accredited voters belong on the evidence ENTRY (entries can differ), not the unit result.

So on pu_results:
  drop chosen_evidence_id   (no single chosen row)
  drop accredited_voters    (lives on evidence, which already has the column)

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_col(insp, table, col) -> bool:
    return insp.has_table(table) and any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _has_col(insp, "pu_results", "chosen_evidence_id"):
        op.drop_column("pu_results", "chosen_evidence_id")
    if _has_col(insp, "pu_results", "accredited_voters"):
        op.drop_column("pu_results", "accredited_voters")


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not _has_col(insp, "pu_results", "chosen_evidence_id"):
        op.add_column("pu_results", sa.Column("chosen_evidence_id", sa.Integer(), nullable=True))
    if not _has_col(insp, "pu_results", "accredited_voters"):
        op.add_column("pu_results", sa.Column("accredited_voters", sa.Integer(), nullable=True))
