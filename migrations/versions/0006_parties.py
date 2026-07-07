"""add parties + party_elections; reseed predictions for new presidential party set

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "parties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("acronym", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("chairman", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("secretary", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("treasurer", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("financial_secretary", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("legal_adviser", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_parties_acronym", "parties", ["acronym"], unique=True)

    op.create_table(
        "party_elections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("party_acronym", sa.String(length=20), nullable=False),
        sa.Column("election_type", sa.String(length=30), nullable=False),
    )
    op.create_index("ix_party_elections_party_acronym", "party_elections", ["party_acronym"])
    op.create_index("ix_party_elections_election_type", "party_elections", ["election_type"])

    # Presidential now uses a different party set (APC, PDP, NDC, NNPP, ADC, LP).
    # Clear predictions so startup reseeds them with the election-specific party sets.
    op.execute("DELETE FROM predictions")


def downgrade() -> None:
    op.drop_index("ix_party_elections_election_type", table_name="party_elections")
    op.drop_index("ix_party_elections_party_acronym", table_name="party_elections")
    op.drop_table("party_elections")
    op.drop_index("ix_parties_acronym", table_name="parties")
    op.drop_table("parties")
