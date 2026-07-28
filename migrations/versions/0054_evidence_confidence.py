"""evidence.confidence — a 0-100 trust score per piece of evidence.

Mirrors pu_results.confidence but at the evidence level: each transcription/recording
carries its own score so we can compare readings and weight the merge. The first signal
is the quality of the sheet the reading came from (missing/blurry/inflated = low, clean =
high) — see app/confidence.py. Nullable: a row with no score yet is distinct from 0.

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("evidence")}
    if "confidence" not in cols:
        op.add_column("evidence", sa.Column("confidence", sa.Integer(), nullable=True))
        op.create_index("ix_evidence_confidence", "evidence", ["confidence"])


def downgrade() -> None:
    op.drop_index("ix_evidence_confidence", table_name="evidence")
    op.drop_column("evidence", "confidence")
