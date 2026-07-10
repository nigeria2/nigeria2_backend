"""complete the canonical lga table to all 774, add lga.geo_id, re-link references

Reconciles the canonical `lga` table against the authoritative 774-LGA list
(backend/app/data/lgas.json, from the official ward dataset): existing rows are matched
by name within their state and kept (id stable — assessments reference these ids),
their name corrected and geo_id set; LGAs missing from the table are inserted. Then
lga_id is re-backfilled on every referencing table now that the canonical list is
complete.

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-10

"""
import difflib
import json
import pathlib
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from app.geo import state_geo_id

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REF_TABLES = ["lga_results", "wards", "ward_results", "polling_units", "problem_units"]
_LGAS_JSON = pathlib.Path(__file__).resolve().parent.parent.parent / "app" / "data" / "lgas.json"


_DIRS = {"north", "south", "east", "west", "central"}


def _norm(s: str) -> str:
    return "".join(c for c in str(s or "").lower() if c.isalnum())


def _dirs(name: str) -> frozenset:
    return frozenset(t for t in str(name or "").lower().replace("-", " ").replace("/", " ").split() if t in _DIRS)


def _match_exact(cands, name, claimed):
    """Exact-normalised or unambiguous-prefix match only (no fuzzy). Safe first pass."""
    n = _norm(name)
    for cn, cid, _raw in cands:
        if cn == n and cid not in claimed:
            return cid
    pref = [cid for cn, cid, _raw in cands if cid not in claimed and (cn.startswith(n) or n.startswith(cn)) and min(len(cn), len(n)) >= 4]
    if len(pref) == 1:
        return pref[0]
    return None


def _match_fuzzy(cands, name, claimed):
    """Close spelling variant, but never across two *different* directional words
    (Afikpo North vs Afikpo South stay distinct; "Centtral"->"Central" still matches
    since the typo carries no directional token)."""
    n = _norm(name)
    d = _dirs(name)
    pool = [(cn, cid) for cn, cid, raw in cands if cid not in claimed and not (d and _dirs(raw) and d != _dirs(raw))]
    close = difflib.get_close_matches(n, [cn for cn, cid in pool], n=1, cutoff=0.82)
    if close:
        for cn, cid in pool:
            if cn == close[0]:
                return cid
    return None


def _match(cands, name, claimed):
    """Backfill matcher for referencing tables (exact/prefix/guarded-fuzzy)."""
    return _match_exact(cands, name, claimed) or _match_fuzzy(cands, name, claimed)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    # Idempotent: the reconciliation may already have been applied out-of-band.
    if "geo_id" not in {c["name"] for c in insp.get_columns("lga")}:
        op.add_column("lga", sa.Column("geo_id", sa.String(length=20), nullable=True))

    authoritative = json.loads(_LGAS_JSON.read_text(encoding="utf-8"))["lgas"]

    existing = defaultdict(list)  # state_geo -> [(norm_name, id, raw_name)]
    for lid, name, sg in conn.execute(text("SELECT id, name, state_geo FROM lga")):
        if sg:
            existing[sg].append((_norm(name), lid, name))

    # Reconcile in two passes so an exact match is never stolen by an earlier
    # entry's fuzzy match: pass 1 exact/prefix, pass 2 guarded fuzzy, then insert.
    claimed: set[int] = set()
    matched: dict[int, dict] = {}  # existing id -> authoritative entry
    pending = []
    for e in authoritative:
        e["_sg"] = state_geo_id(e["state"])
        mid = _match_exact(existing.get(e["_sg"], []), e["name"], claimed)
        if mid is not None:
            claimed.add(mid)
            matched[mid] = e
        else:
            pending.append(e)
    still = []
    for e in pending:
        mid = _match_fuzzy(existing.get(e["_sg"], []), e["name"], claimed)
        if mid is not None:
            claimed.add(mid)
            matched[mid] = e
        else:
            still.append(e)
    for mid, e in matched.items():
        conn.execute(text("UPDATE lga SET name = :n, geo_id = :g WHERE id = :i"),
                     {"n": e["name"], "g": e["geo_id"], "i": mid})
    for e in still:
        conn.execute(text("INSERT INTO lga (state, state_geo, name, geo_id) VALUES (:s, :sg, :n, :g)"),
                     {"s": e["state"], "sg": e["_sg"], "n": e["name"], "g": e["geo_id"]})
    if "ix_lga_geo_id" not in {i["name"] for i in insp.get_indexes("lga")}:
        op.create_index("ix_lga_geo_id", "lga", ["geo_id"])

    # re-backfill lga_id on referencing tables against the now-complete canonical
    canon = defaultdict(list)  # state_geo -> [(norm_name, id, raw_name)]
    for lid, name, sg in conn.execute(text("SELECT id, name, state_geo FROM lga")):
        if sg:
            canon[sg].append((_norm(name), lid, name))
    for table in _REF_TABLES:
        pairs = conn.execute(text(f'SELECT DISTINCT state_geo, lga FROM "{table}" WHERE lga_id IS NULL')).all()
        rows = []
        for sg, raw in pairs:
            if not raw:
                continue
            mid = _match(canon.get(sg, []), raw, set())
            if mid is not None:
                rows.append((sg, raw, mid))
        if rows:
            values = ", ".join(f"(:s{i}, :r{i}, :i{i})" for i in range(len(rows)))
            params = {}
            for i, (sg, raw, mid) in enumerate(rows):
                params[f"s{i}"], params[f"r{i}"], params[f"i{i}"] = sg, raw, mid
            conn.execute(
                text(
                    f'UPDATE "{table}" AS t SET lga_id = m.lid::integer '
                    f'FROM (VALUES {values}) AS m(sg, raw, lid) '
                    f'WHERE t.state_geo = m.sg AND t.lga = m.raw AND t.lga_id IS NULL'
                ),
                params,
            )


def downgrade() -> None:
    op.drop_index("ix_lga_geo_id", table_name="lga")
    op.drop_column("lga", "geo_id")
