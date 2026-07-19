"""evidence.priority — higher-priority evidence wins the merge

A merge-priority integer on evidence (default 0). build_results picks the highest-priority
evidence per (polling unit, office) before falling back to kind order, so a manual correction
(e.g. zeroing a misread all-parties-inflated sheet) can be loaded as new higher-priority
evidence and win over the raw transcription without deleting it.

Revision ID: 0051
Revises: 0050
Create Date: 2026-07-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("evidence")}
    if "priority" not in cols:
        op.add_column("evidence", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
        have = {i["name"] for i in insp.get_indexes("evidence")}
        if "ix_evidence_priority" not in have:
            op.create_index("ix_evidence_priority", "evidence", ["priority"])


def downgrade() -> None:
    op.drop_index("ix_evidence_priority", table_name="evidence")
    op.drop_column("evidence", "priority")
