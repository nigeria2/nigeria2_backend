"""prediction scenarios + resumable model jobs

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- extend state_predictions with model provenance ---
    op.add_column("state_predictions", sa.Column("scenario_id", sa.Integer(), nullable=True))
    op.add_column("state_predictions", sa.Column("detail", sa.Text(), nullable=False, server_default="{}"))
    op.create_index("ix_state_predictions_scenario_id", "state_predictions", ["scenario_id"])

    # --- scenarios ---
    op.create_table(
        "prediction_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("election_type", sa.String(length=30), nullable=False, server_default="presidential"),
        sa.Column("base_year", sa.String(length=10), nullable=False, server_default="2023"),
        sa.Column("target_year", sa.String(length=10), nullable=False, server_default="2027"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("log", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_prediction_scenarios_status", "prediction_scenarios", ["status"])

    # --- scenario politicians ---
    op.create_table(
        "scenario_politicians",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("politician_id", sa.Integer(), nullable=False),
        sa.Column("politician_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("new_party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("delta_popularity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("influence_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="local"),
        sa.Column("home_state", sa.String(length=50), nullable=False, server_default=""),
    )
    op.create_index("ix_scenario_politicians_scenario_id", "scenario_politicians", ["scenario_id"])
    op.create_index("ix_scenario_politicians_politician_id", "scenario_politicians", ["politician_id"])

    # --- scenario trends ---
    op.create_table(
        "scenario_trends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("shift_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("target_party", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("scope_states", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_scenario_trends_scenario_id", "scenario_trends", ["scenario_id"])

    # --- drop the seeded 2023 past-performance predictions (removed feature) ---
    op.execute("DELETE FROM state_predictions WHERE source = 'past_performance'")


def downgrade() -> None:
    op.drop_index("ix_scenario_trends_scenario_id", table_name="scenario_trends")
    op.drop_table("scenario_trends")
    op.drop_index("ix_scenario_politicians_politician_id", table_name="scenario_politicians")
    op.drop_index("ix_scenario_politicians_scenario_id", table_name="scenario_politicians")
    op.drop_table("scenario_politicians")
    op.drop_index("ix_prediction_scenarios_status", table_name="prediction_scenarios")
    op.drop_table("prediction_scenarios")
    op.drop_index("ix_state_predictions_scenario_id", table_name="state_predictions")
    op.drop_column("state_predictions", "detail")
    op.drop_column("state_predictions", "scenario_id")
