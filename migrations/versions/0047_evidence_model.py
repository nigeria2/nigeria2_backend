"""Reframe transcriptions as EVIDENCE: rename tables/cols + add evidence.kind

Every recorded number for a polling unit is a piece of EVIDENCE. The INEC-reported
figure is the first piece of evidence (kind='inec'); LLM-transcribed and human-transcribed
sheets are further evidence. `pu_result` is the DERIVED definitive that points at the
chosen evidence. So any unit with a result always has >=1 evidence row.

Renames (idempotent):
  sheet_transcriptions            -> evidence           (+ new column `kind`)
  transcription_parties           -> evidence_parties   (transcription_id -> evidence_id)
  pu_results.chosen_transcription_id -> chosen_evidence_id

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_col(insp, table, col) -> bool:
    return insp.has_table(table) and any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # evidence table (was sheet_transcriptions)
    if insp.has_table("sheet_transcriptions") and not insp.has_table("evidence"):
        op.rename_table("sheet_transcriptions", "evidence")
    insp = sa.inspect(conn)
    if insp.has_table("evidence"):
        if not _has_col(insp, "evidence", "kind"):
            # kind: inec | llm | human | crowd | ...  (type of evidence; default 'inec')
            op.add_column("evidence", sa.Column("kind", sa.String(length=20), nullable=False, server_default="inec"))
        # provenance: `source` = where it came from (INEC IReV, an LLM model name, a sheet
        # id/url); `submitted_by` = the user who added it (for weighting). Both already
        # exist as columns from the old schema; ensure they are widened + indexed.
        if _has_col(insp, "evidence", "source"):
            op.alter_column("evidence", "source", type_=sa.String(length=120))
        if not _has_col(insp, "evidence", "submitted_by_id"):
            op.add_column("evidence", sa.Column("submitted_by_id", sa.Integer(), nullable=True))  # users.id, for weighting
        have = {i["name"] for i in insp.get_indexes("evidence")}
        for col in ("kind", "source", "submitted_by", "submitted_by_id"):
            name = f"ix_evidence_{col}"
            if name not in have and _has_col(sa.inspect(conn), "evidence", col):
                op.create_index(name, "evidence", [col])

    # evidence_parties (was transcription_parties; transcription_id -> evidence_id)
    if insp.has_table("transcription_parties") and not insp.has_table("evidence_parties"):
        op.rename_table("transcription_parties", "evidence_parties")
    insp = sa.inspect(conn)
    if _has_col(insp, "evidence_parties", "transcription_id") and not _has_col(insp, "evidence_parties", "evidence_id"):
        op.alter_column("evidence_parties", "transcription_id", new_column_name="evidence_id")
    # 0043's _party_table created this without votes_words and with votes NOT NULL,
    # which mismatched the model. Reconcile so evidence can carry the verbatim words and
    # a blank figure.
    if insp.has_table("evidence_parties"):
        if not _has_col(insp, "evidence_parties", "votes_words"):
            op.add_column("evidence_parties", sa.Column("votes_words", sa.String(length=120), nullable=False, server_default=""))
        op.alter_column("evidence_parties", "votes", nullable=True)

    # pu_results.chosen_transcription_id -> chosen_evidence_id
    insp = sa.inspect(conn)
    if _has_col(insp, "pu_results", "chosen_transcription_id") and not _has_col(insp, "pu_results", "chosen_evidence_id"):
        op.alter_column("pu_results", "chosen_transcription_id", new_column_name="chosen_evidence_id")


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _has_col(insp, "pu_results", "chosen_evidence_id") and not _has_col(insp, "pu_results", "chosen_transcription_id"):
        op.alter_column("pu_results", "chosen_evidence_id", new_column_name="chosen_transcription_id")
    if _has_col(insp, "evidence_parties", "evidence_id") and not _has_col(insp, "evidence_parties", "transcription_id"):
        op.alter_column("evidence_parties", "evidence_id", new_column_name="transcription_id")
    if insp.has_table("evidence_parties") and not insp.has_table("transcription_parties"):
        op.rename_table("evidence_parties", "transcription_parties")
    if insp.has_table("evidence"):
        if _has_col(insp, "evidence", "kind"):
            op.drop_column("evidence", "kind")
        if not insp.has_table("sheet_transcriptions"):
            op.rename_table("evidence", "sheet_transcriptions")
