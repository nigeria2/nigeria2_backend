"""link LGA-name tables to the canonical `lga` table by id, and correct names

The `lga` table is the single source of truth for LGA names. This adds `lga_id` to
every table that stored an LGA name string (some truncated, e.g. "Ikot-Ekp" from the
geojson), backfills it by matching the stored name to the canonical LGA within the same
state (exact/prefix-normalised), and rewrites the stored name to the canonical spelling.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-10

"""
import difflib
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ["lga_results", "wards", "ward_results", "polling_units", "problem_units"]


def _norm(s: str) -> str:
    return "".join(c for c in str(s or "").lower() if c.isalnum())


def _build_resolver(conn):
    """state_geo -> list of (norm_name, id, canonical_name) for the canonical LGAs."""
    per: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for lid, name, sg in conn.execute(text('SELECT id, name, state_geo FROM lga')):
        if sg:
            per[sg].append((_norm(name), lid, name))
    return per


def _resolve(per, sg: str, raw: str):
    """(lga_id, canonical_name) for a stored name within a state, or (None, None)."""
    n = _norm(raw)
    if not n:
        return None, None
    cands = per.get(sg, [])
    for cn, cid, cname in cands:
        if cn == n:
            return cid, cname
    # stored name truncated -> unique canonical that it's a prefix of
    pref = [(cid, cname) for cn, cid, cname in cands if cn.startswith(n) and len(n) >= 3]
    if len(pref) == 1:
        return pref[0]
    # stored name longer -> unique canonical that is a prefix of it
    pref2 = [(cid, cname) for cn, cid, cname in cands if n.startswith(cn) and len(cn) >= 3]
    if len(pref2) == 1:
        return pref2[0]
    # close spelling variant (Somolu/Shomolu, Badagry/Badagary): high cutoff so a
    # genuinely different LGA (Ahiazu Mbaise) is not matched to a namesake.
    by_norm = {cn: (cid, cname) for cn, cid, cname in cands}
    close = difflib.get_close_matches(n, list(by_norm), n=1, cutoff=0.9)
    if close:
        return by_norm[close[0]]
    return None, None


def upgrade() -> None:
    conn = op.get_bind()
    per = _build_resolver(conn)
    for table in _TABLES:
        op.add_column(table, sa.Column("lga_id", sa.Integer(), nullable=True))
        pairs = conn.execute(text(f'SELECT DISTINCT state_geo, lga FROM "{table}"')).all()
        rows = []  # (state_geo, raw_name, lga_id, canonical_name)
        for sg, raw in pairs:
            if not raw:
                continue
            lid, cname = _resolve(per, sg, raw)
            if lid is not None:
                rows.append((sg, raw, lid, cname))
        if rows:
            values = ", ".join(f"(:s{i}, :r{i}, :i{i}, :c{i})" for i in range(len(rows)))
            params = {}
            for i, (sg, raw, lid, cname) in enumerate(rows):
                params[f"s{i}"], params[f"r{i}"], params[f"i{i}"], params[f"c{i}"] = sg, raw, lid, cname
            # lga_results held truncated names ("Ikot-Ekp") so rewrite them to the
            # canonical spelling. The other tables carry the INEC name (often more
            # correct than canonical), so only attach the id there — never overwrite.
            set_name = ", lga = m.cn" if table == "lga_results" else ""
            conn.execute(
                text(
                    f'UPDATE "{table}" AS t SET lga_id = m.lid::integer{set_name} '
                    f'FROM (VALUES {values}) AS m(sg, raw, lid, cn) '
                    f'WHERE t.state_geo = m.sg AND t.lga = m.raw'
                ),
                params,
            )
        op.create_index(f"ix_{table}_lga_id", table, ["lga_id"])


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_lga_id", table_name=table)
        op.drop_column(table, "lga_id")
