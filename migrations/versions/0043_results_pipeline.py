"""Unified results pipeline: transcriptions + per-level results (party long-form)

Creates the normalized results architecture:
  sheet_transcriptions + transcription_parties  (submissions of a sheet)
  pu_results + pu_result_parties                (definitive polling-unit result)
  ward_result_v + ward_result_parties           (ward level, directly writable or rolled up)
  lga_result_v  + lga_result_parties            (LGA level)
  state_result_v + state_result_parties         (state level; where state-only data lives)

Every *_result table carries `source` (declared|rolled_up|official). Votes are
always long form in the paired `*_part*` table so the model is party-agnostic.

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _party_table(name: str, parent_fk: str) -> None:
    """A long-form party-votes child table: (id, <parent_fk>, party, votes)."""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(name):
        op.create_table(
            name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(parent_fk, sa.Integer(), nullable=False, server_default="0"),
            sa.Column("party", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        )
    _index(name, (parent_fk, "party"))


def _index(table: str, cols) -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return
    have = {i["name"] for i in insp.get_indexes(table)}
    for col in cols:
        name = f"ix_{table}_{col}"
        if name not in have:
            op.create_index(name, table, [col])


def _result_common():
    """Columns shared by every *_result_v level table (minus the geo keys). Built
    fresh each call — a Column instance can only belong to one table."""
    return [
        sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
        sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
        sa.Column("state_geo", sa.String(length=20), nullable=True),
        sa.Column("winner", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("runner_up", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("total_votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_votes", sa.Integer(), nullable=True),
        sa.Column("registered_voters", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="declared"),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    # --- transcriptions -----------------------------------------------------
    if not insp.has_table("sheet_transcriptions"):
        op.create_table(
            "sheet_transcriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sheet_id", sa.Integer(), nullable=True),
            sa.Column("pu_code", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("source", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("method", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("submitted_by", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("registered_voters", sa.Integer(), nullable=True),
            sa.Column("accredited_voters", sa.Integer(), nullable=True),
            sa.Column("valid_votes", sa.Integer(), nullable=True),
            sa.Column("rejected_votes", sa.Integer(), nullable=True),
            sa.Column("total_used_ballots", sa.Integer(), nullable=True),
            sa.Column("raw", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    _index("sheet_transcriptions", ("sheet_id", "pu_code", "election_type", "year", "state_geo"))
    _party_table("transcription_parties", "transcription_id")

    # --- definitive polling-unit result -------------------------------------
    if not insp.has_table("pu_results"):
        op.create_table(
            "pu_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pu_code", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("election_type", sa.String(length=20), nullable=False, server_default="presidential"),
            sa.Column("year", sa.String(length=10), nullable=False, server_default="2023"),
            sa.Column("state_geo", sa.String(length=20), nullable=True),
            sa.Column("lga_id", sa.Integer(), nullable=True),
            sa.Column("ward_code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("winner", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("runner_up", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("total_votes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("valid_votes", sa.Integer(), nullable=True),
            sa.Column("registered_voters", sa.Integer(), nullable=True),
            sa.Column("accredited_voters", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=30), nullable=False, server_default="declared"),
            sa.Column("chosen_transcription_id", sa.Integer(), nullable=True),
            sa.Column("method", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    _index("pu_results", ("pu_code", "election_type", "year", "state_geo", "lga_id", "ward_code"))
    _party_table("pu_result_parties", "pu_result_id")

    # --- ward level ---------------------------------------------------------
    if not insp.has_table("ward_result_v"):
        op.create_table(
            "ward_result_v",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ward_code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("lga_id", sa.Integer(), nullable=True),
            sa.Column("ward", sa.String(length=160), nullable=False, server_default=""),
            *_result_common(),
        )
    _index("ward_result_v", ("ward_code", "election_type", "year", "state_geo", "lga_id"))
    _party_table("ward_result_parties", "ward_result_id")

    # --- LGA level ----------------------------------------------------------
    if not insp.has_table("lga_result_v"):
        op.create_table(
            "lga_result_v",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("lga_id", sa.Integer(), nullable=True),
            sa.Column("lga", sa.String(length=120), nullable=False, server_default=""),
            *_result_common(),
        )
    _index("lga_result_v", ("lga_id", "election_type", "year", "state_geo"))
    _party_table("lga_result_parties", "lga_result_id")

    # --- state level --------------------------------------------------------
    if not insp.has_table("state_result_v"):
        op.create_table(
            "state_result_v",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("state", sa.String(length=60), nullable=False, server_default=""),
            *_result_common(),
        )
    _index("state_result_v", ("election_type", "year", "state_geo"))
    _party_table("state_result_parties", "state_result_id")


def downgrade() -> None:
    for t in (
        "state_result_parties", "state_result_v",
        "lga_result_parties", "lga_result_v",
        "ward_result_parties", "ward_result_v",
        "pu_result_parties", "pu_results",
        "transcription_parties", "sheet_transcriptions",
    ):
        op.drop_table(t)
