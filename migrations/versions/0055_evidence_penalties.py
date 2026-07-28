"""evidence_penalties — audit trail of confidence deductions per piece of evidence.

Some evidence readings are demonstrably wrong (e.g. an OCR misread giving a minor party
thousands of votes). Rather than silently lowering a score, every deduction is RECORDED
here: which evidence/polling unit, why, and how many points came off. `evidence.confidence`
is lowered by the same amount; this table explains the number and drives the hover on the
site.

Revision ID: 0055
Revises: 0054
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("evidence_penalties"):
        op.create_table(
            "evidence_penalties",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("evidence_id", sa.Integer(), nullable=False),   # FK evidence.id
            sa.Column("pu_code", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
            sa.Column("rule", sa.String(length=60), nullable=False, server_default=""),  # short slug of the rule
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),           # human-readable why
            sa.Column("party", sa.String(length=20), nullable=False, server_default=""), # offending party (if any)
            sa.Column("votes", sa.Integer(), nullable=True),                             # offending vote figure
            sa.Column("points", sa.Integer(), nullable=False, server_default="0"),       # points deducted
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    insp = sa.inspect(op.get_bind())
    have = {i["name"] for i in insp.get_indexes("evidence_penalties")}
    for col in ("evidence_id", "pu_code", "rule"):
        name = f"ix_evidence_penalties_{col}"
        if name not in have:
            op.create_index(name, "evidence_penalties", [col])


def downgrade() -> None:
    op.drop_table("evidence_penalties")
