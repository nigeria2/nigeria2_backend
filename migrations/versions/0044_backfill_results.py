"""Backfill legacy results into the unified *_result_v tables (source='declared')

Copies what we already have so the results pages keep working on the new schema:
  ward_results       -> ward_result_v  (+ ward_result_parties: APC/LP/PDP/NNPP)
  lga_party_results  -> lga_result_v   (+ lga_result_parties: full party set)
  state_presidential -> state_result_v (+ state_result_parties: APC/PDP/LP/NNPP/Others)

Idempotent & data-only: deletes any prior source='declared' rows (and their party
children) first, then reloads. The definitive-picker later writes source='rolled_up'
rows separately; those are left untouched.

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clear_declared(conn, result_table: str, party_table: str, fk: str) -> None:
    """Remove previously-backfilled declared rows (+ their party children) so this
    migration is safely re-runnable without duplicating."""
    conn.execute(sa.text(
        f"DELETE FROM {party_table} WHERE {fk} IN "
        f"(SELECT id FROM {result_table} WHERE source = 'declared')"
    ))
    conn.execute(sa.text(f"DELETE FROM {result_table} WHERE source = 'declared'"))


def _winner_runner(pairs: list[tuple[str, int]]) -> tuple[str, str]:
    ranked = sorted((p for p in pairs if p[1]), key=lambda x: x[1], reverse=True)
    winner = ranked[0][0] if ranked else ""
    runner = ranked[1][0] if len(ranked) > 1 else ""
    return winner, runner


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # --- ward_results -> ward_result_v (presidential, APC/LP/PDP/NNPP) -------
    if insp.has_table("ward_results") and insp.has_table("ward_result_v"):
        _clear_declared(conn, "ward_result_v", "ward_result_parties", "ward_result_id")
        rows = conn.execute(sa.text(
            "SELECT ward_code, ward, lga_id, state_geo, votes_apc, votes_lp, votes_pdp, "
            "votes_nnpp, total_votes, winner, runner_up FROM ward_results"
        )).mappings().all()
        for r in rows:
            res = conn.execute(sa.text(
                "INSERT INTO ward_result_v (ward_code, ward, lga_id, election_type, year, "
                "state_geo, winner, runner_up, total_votes, source) VALUES "
                "(:ward_code, :ward, :lga_id, 'presidential', '2023', :state_geo, :winner, "
                ":runner_up, :total_votes, 'declared')"
            ), dict(r))
            wid = res.lastrowid if res.lastrowid else conn.execute(sa.text(
                "SELECT id FROM ward_result_v WHERE ward_code=:c AND election_type='presidential' "
                "AND year='2023' AND source='declared' ORDER BY id DESC LIMIT 1"
            ), {"c": r["ward_code"]}).scalar()
            for party, col in (("APC", "votes_apc"), ("LP", "votes_lp"), ("PDP", "votes_pdp"), ("NNPP", "votes_nnpp")):
                conn.execute(sa.text(
                    "INSERT INTO ward_result_parties (ward_result_id, party, votes) "
                    "VALUES (:wid, :party, :votes)"
                ), {"wid": wid, "party": party, "votes": r[col] or 0})

    # --- lga_party_results -> lga_result_v (presidential + governor) --------
    if insp.has_table("lga_party_results") and insp.has_table("lga_result_v"):
        _clear_declared(conn, "lga_result_v", "lga_result_parties", "lga_result_id")
        # group long-form party rows per (election_type, year, lga)
        groups: dict = {}
        for r in conn.execute(sa.text(
            "SELECT election_type, year, state_geo, lga_id, lga, party, votes FROM lga_party_results"
        )).mappings().all():
            key = (r["election_type"], r["year"], r["state_geo"], r["lga_id"], r["lga"])
            groups.setdefault(key, []).append((r["party"], r["votes"] or 0))
        for (et, year, sgeo, lga_id, lga), parties in groups.items():
            winner, runner = _winner_runner(parties)
            total = sum(v for _, v in parties)
            res = conn.execute(sa.text(
                "INSERT INTO lga_result_v (lga_id, lga, election_type, year, state_geo, "
                "winner, runner_up, total_votes, source) VALUES "
                "(:lga_id, :lga, :et, :year, :sgeo, :winner, :runner, :total, 'declared')"
            ), {"lga_id": lga_id, "lga": lga, "et": et, "year": year, "sgeo": sgeo,
                "winner": winner, "runner": runner, "total": total})
            lid = res.lastrowid if res.lastrowid else conn.execute(sa.text(
                "SELECT id FROM lga_result_v WHERE election_type=:et AND year=:year AND lga=:lga "
                "AND source='declared' ORDER BY id DESC LIMIT 1"
            ), {"et": et, "year": year, "lga": lga}).scalar()
            for party, votes in parties:
                conn.execute(sa.text(
                    "INSERT INTO lga_result_parties (lga_result_id, party, votes) "
                    "VALUES (:lid, :party, :votes)"
                ), {"lid": lid, "party": party, "votes": votes})

    # --- state_presidential -> state_result_v (presidential) ----------------
    if insp.has_table("state_presidential") and insp.has_table("state_result_v"):
        _clear_declared(conn, "state_result_v", "state_result_parties", "state_result_id")
        for r in conn.execute(sa.text(
            "SELECT state, state_geo, year, apc, pdp, lp, nnpp, others, total_votes, winner "
            "FROM state_presidential"
        )).mappings().all():
            parts = [("APC", r["apc"] or 0), ("PDP", r["pdp"] or 0), ("LP", r["lp"] or 0),
                     ("NNPP", r["nnpp"] or 0), ("Others", r["others"] or 0)]
            winner = r["winner"] or _winner_runner(parts)[0]
            _, runner = _winner_runner(parts)
            total = r["total_votes"] or sum(v for _, v in parts)
            res = conn.execute(sa.text(
                "INSERT INTO state_result_v (state, state_geo, election_type, year, winner, "
                "runner_up, total_votes, source) VALUES "
                "(:state, :sgeo, 'presidential', :year, :winner, :runner, :total, 'declared')"
            ), {"state": r["state"], "sgeo": r["state_geo"], "year": str(r["year"]),
                "winner": winner, "runner": runner, "total": total})
            sid = res.lastrowid if res.lastrowid else conn.execute(sa.text(
                "SELECT id FROM state_result_v WHERE election_type='presidential' AND year=:year "
                "AND state=:state AND source='declared' ORDER BY id DESC LIMIT 1"
            ), {"year": str(r["year"]), "state": r["state"]}).scalar()
            for party, votes in parts:
                if votes:
                    conn.execute(sa.text(
                        "INSERT INTO state_result_parties (state_result_id, party, votes) "
                        "VALUES (:sid, :party, :votes)"
                    ), {"sid": sid, "party": party, "votes": votes})


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    for res_t, party_t, fk in (
        ("ward_result_v", "ward_result_parties", "ward_result_id"),
        ("lga_result_v", "lga_result_parties", "lga_result_id"),
        ("state_result_v", "state_result_parties", "state_result_id"),
    ):
        if insp.has_table(res_t):
            _clear_declared(conn, res_t, party_t, fk)
