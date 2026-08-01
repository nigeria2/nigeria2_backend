"""create data_reports table

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("pu_code", sa.String(length=30), nullable=True),
        sa.Column("ward_code", sa.String(length=30), nullable=True),
        sa.Column("lga_id", sa.Integer(), nullable=True),
        sa.Column("state_geo", sa.String(length=20), nullable=True),
        sa.Column("year", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("election_type", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_data_reports_level", "data_reports", ["level"])
    op.create_index("ix_data_reports_pu_code", "data_reports", ["pu_code"])
    op.create_index("ix_data_reports_ward_code", "data_reports", ["ward_code"])
    op.create_index("ix_data_reports_lga_id", "data_reports", ["lga_id"])
    op.create_index("ix_data_reports_state_geo", "data_reports", ["state_geo"])


def downgrade() -> None:
    op.drop_index("ix_data_reports_state_geo", table_name="data_reports")
    op.drop_index("ix_data_reports_lga_id", table_name="data_reports")
    op.drop_index("ix_data_reports_ward_code", table_name="data_reports")
    op.drop_index("ix_data_reports_pu_code", table_name="data_reports")
    op.drop_index("ix_data_reports_level", table_name="data_reports")
    op.drop_table("data_reports")
