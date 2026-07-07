"""add problem_units (2023 anomaly polling units)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "problem_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("lga", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("ward", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("polling_unit", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("pu_code", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("anomaly_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="High"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("registered_voters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accredited_voters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("votes_cast", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("election_year", sa.String(length=10), nullable=False, server_default="2023"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_problem_units_state", "problem_units", ["state"])
    op.create_index("ix_problem_units_anomaly_type", "problem_units", ["anomaly_type"])


def downgrade() -> None:
    op.drop_index("ix_problem_units_anomaly_type", table_name="problem_units")
    op.drop_index("ix_problem_units_state", table_name="problem_units")
    op.drop_table("problem_units")
