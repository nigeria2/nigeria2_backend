"""Per-level evidence: ward_evidence / lga_evidence / state_evidence (+ parties)

Every geo level's score is a MERGE of its evidence. That evidence has two possible
origins: (a) a roll-up from the level below (the child results are evidence for the
parent's score), and (b) independent figures recorded directly at this level from another
source (e.g. an INEC-declared LGA total, a collation-centre figure). So evidence exists at
each level, mirroring the polling-unit `evidence` table.

Tables (each with a long-form `*_parties` child holding one row per party):
  ward_evidence   (ward_code)   + ward_evidence_parties
  lga_evidence    (lga_id)      + lga_evidence_parties
  state_evidence  (state_geo)   + state_evidence_parties

`kind`: 'rollup' (computed from the level below) OR an independent source
        (inec_declared | collation | 2023_transcription | ...).

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0049"
down_revision: Union[str, None] = "0048"
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


def _evidence_table(name: str, geo_col: sa.Column | None, geo_idx: str) -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(name):
        cols = [sa.Column("id", sa.Integer(), primary_key=True)]
        if geo_col is not None:
            cols.append(geo_col)
        op.create_table(
            name,
            *cols,
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("kind", sa.String(length=30), nullable=False, server_default="rollup"),
            sa.Column("source", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("method", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("registered_voters", sa.Integer(), nullable=True),
            sa.Column("accredited_voters", sa.Integer(), nullable=True),
            sa.Column("valid_votes", sa.Integer(), nullable=True),
            sa.Column("rejected_votes", sa.Integer(), nullable=True),
            sa.Column("total_votes", sa.Integer(), nullable=True),
            sa.Column("raw", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    _idx(name, (geo_idx, "election_type", "year", "state_geo", "kind"))


def _parties_table(name: str, fk: str) -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(name):
        op.create_table(
            name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(fk, sa.Integer(), nullable=False, server_default="0"),
            sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("votes", sa.Integer(), nullable=True),
            sa.Column("votes_words", sa.String(length=120), nullable=False, server_default=""),
        )
    _idx(name, (fk, "party"))


def upgrade() -> None:
    _evidence_table("ward_evidence", sa.Column("ward_code", sa.String(length=30), nullable=False, server_default=""), "ward_code")
    _parties_table("ward_evidence_parties", "ward_evidence_id")
    _evidence_table("lga_evidence", sa.Column("lga_id", sa.Integer(), nullable=True), "lga_id")
    _parties_table("lga_evidence_parties", "lga_evidence_id")
    # state level: the geo key IS state_geo (already a common column), no extra geo column
    _evidence_table("state_evidence", None, "state_geo")
    _parties_table("state_evidence_parties", "state_evidence_id")


def downgrade() -> None:
    for t in ("ward_evidence_parties", "ward_evidence",
              "lga_evidence_parties", "lga_evidence",
              "state_evidence_parties", "state_evidence"):
        op.drop_table(t)
