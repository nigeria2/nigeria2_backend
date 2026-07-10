"""add geo_id / state_geo columns and backfill from state names

Every table that keyed on a state *name* gains a geo-id column (states.geo_id,
<table>.state_geo, or <table>.home_state_geo) backfilled from the existing name via
app.geo. Name columns are kept for display; all lookups switch to the geo id.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from app.geo import state_geo_id

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, name column, new geo column). states carries the canonical geo_id.
_TABLES: list[tuple[str, str, str]] = [
    ("states", "name", "geo_id"),
    ("interested_users", "state", "state_geo"),
    ("users", "home_state", "home_state_geo"),
    ("predictions", "state", "state_geo"),
    ("state_predictions", "state", "state_geo"),
    ("scenario_politicians", "home_state", "home_state_geo"),
    ("election_results", "state", "state_geo"),
    ("party_history", "state", "state_geo"),
    ("governors", "state", "state_geo"),
    ("governor_history", "state", "state_geo"),
    ("lga_results", "state", "state_geo"),
    ("polling_units", "state", "state_geo"),
    ("ward_results", "state", "state_geo"),
    ("senators", "state", "state_geo"),
    ("state_presidential", "state", "state_geo"),
    ("house_members", "state", "state_geo"),
    ("wards", "state", "state_geo"),
    ("lga", "state", "state_geo"),
    ("politicians", "state", "state_geo"),
    ("problem_units", "state", "state_geo"),
    ("declared_candidates", "state", "state_geo"),
    ("analyses", "state", "state_geo"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for table, name_col, geo_col in _TABLES:
        op.add_column(table, sa.Column(geo_col, sa.String(length=20), nullable=True))
        # backfill in one pass: map each distinct present name to its geo id, then a
        # single UPDATE ... FROM (VALUES ...) join (one scan even on large tables).
        names = [r[0] for r in bind.execute(text(f'SELECT DISTINCT "{name_col}" FROM "{table}"')).all()]
        pairs = [(nm, state_geo_id(nm)) for nm in names if nm and state_geo_id(nm)]
        if pairs:
            values = ", ".join(f"(:n{i}, :g{i})" for i in range(len(pairs)))
            params = {}
            for i, (nm, gid) in enumerate(pairs):
                params[f"n{i}"], params[f"g{i}"] = nm, gid
            bind.execute(
                text(
                    f'UPDATE "{table}" AS t SET "{geo_col}" = m.gid '
                    f'FROM (VALUES {values}) AS m(nm, gid) WHERE t."{name_col}" = m.nm'
                ),
                params,
            )
        idx = f"ix_{table}_{geo_col}"
        op.create_index(idx, table, [geo_col], unique=(table == "states"))


def downgrade() -> None:
    for table, _name_col, geo_col in reversed(_TABLES):
        op.drop_index(f"ix_{table}_{geo_col}", table_name=table)
        op.drop_column(table, geo_col)
