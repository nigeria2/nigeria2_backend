"""pu_results.confidence — a 0-100 quality/trust score per polling-unit result.

The first signal that flows in is SHEET QUALITY: a result built from a missing sheet
location, a blurry/illegible scan, or an auto-voided inflated misread is low
confidence; a clean saved sheet is high. The score is stored so we can (a) show it on
the polling-unit page and (b) exclude low-confidence units from the ward/LGA/state
roll-up (build_results --min-confidence). `confidence_band` is a derived label
(high >=80, medium 50-79, low <50) for quick display/filtering.

Revision ID: 0053
Revises: 0052
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("pu_results")}
    if "confidence" not in cols:
        # nullable: a result with no score yet is distinct from a scored-0 (voided) result
        op.add_column("pu_results", sa.Column("confidence", sa.Integer(), nullable=True))
        op.create_index("ix_pu_results_confidence", "pu_results", ["confidence"])
    if "confidence_band" not in cols:
        op.add_column("pu_results", sa.Column(
            "confidence_band", sa.String(length=10), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_index("ix_pu_results_confidence", table_name="pu_results")
    op.drop_column("pu_results", "confidence_band")
    op.drop_column("pu_results", "confidence")
