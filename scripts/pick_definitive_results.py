#!/usr/bin/env python
"""Pick the definitive result for each polling unit and roll it up to ward/LGA/state.

Reads every transcription (submission) we hold per (pu_code, election_type, year),
chooses ONE as definitive via `choose()`, writes it to `pu_results` (+ party rows),
then aggregates upward into `ward_result_v` / `lga_result_v` / `state_result_v`
(source="rolled_up"). Rows that were hand-loaded (source="declared"/"official") at a
coarser level are NEVER deleted just because finer data is missing — the rollup only
adds/refreshes the levels it can actually compute from polling units.

USAGE (run LOCALLY; it talks to the DB via $DATABASE_URL like the app):
    python -m scripts.pick_definitive_results            # dry run (default) — prints, writes nothing
    python -m scripts.pick_definitive_results --commit   # actually write
    python -m scripts.pick_definitive_results --year 2023 --election presidential --commit

⚠️  The selection ALGORITHM is not finalised. `choose()` below is a documented
    placeholder. Specify the real rule, drop it in, then run with --commit.

Do NOT wire this into the API/startup — it is an operator tool.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field

# allow "python scripts/pick_definitive_results.py" as well as "-m scripts...."
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, func as _sa_func, select  # noqa: E402


def func_count():
    return _sa_func.count()
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    SheetTranscription, TranscriptionParty,
    PuResult, PuResultParty,
    WardResultV, WardResultParty,
    LgaResultV, LgaResultParty,
    StateResultV, StateResultParty,
    PollingUnit, Lga,
    # archive models (physical tables *_archive) — read only by --from-archive
    WardResult, LgaResult, LgaPartyResult, StatePresidential,
)


# --------------------------------------------------------------------------- #
# Selection algorithm (PLACEHOLDER — specify the real rule here)
# --------------------------------------------------------------------------- #
@dataclass
class Decision:
    """The chosen definitive figures for one polling unit / election."""
    winner: str = ""
    runner_up: str = ""
    total_votes: int = 0
    valid_votes: int | None = None
    registered_voters: int | None = None
    accredited_voters: int | None = None
    parties: dict[str, int] = field(default_factory=dict)   # party -> votes (may be empty)
    chosen_transcription_id: int | None = None
    method: str = "placeholder"


@dataclass
class Submission:
    """One transcription flattened for the algorithm's convenience."""
    id: int
    source: str
    method: str
    created_at: object
    registered_voters: int | None
    accredited_voters: int | None
    valid_votes: int | None
    parties: dict[str, int]          # party -> votes (blank figures dropped)


def choose(subs: list[Submission]) -> Decision | None:
    """Choose the definitive result for ONE polling unit / election from its
    submissions. Return None to leave the PU without a definitive result.

    ⚠️  PLACEHOLDER POLICY — REPLACE WITH THE REAL ALGORITHM.
    Current stub: pick the most recent submission that has any party figures;
    if none has figures, pick the most recent submission for its summary only.
    """
    if not subs:
        return None
    with_parties = [s for s in subs if s.parties]
    pick = (max(with_parties, key=lambda s: (s.created_at is not None, s.created_at))
            if with_parties else
            max(subs, key=lambda s: (s.created_at is not None, s.created_at)))
    ranked = sorted(pick.parties.items(), key=lambda kv: kv[1], reverse=True)
    winner = ranked[0][0] if ranked else ""
    runner = ranked[1][0] if len(ranked) > 1 else ""
    total = sum(pick.parties.values()) if pick.parties else (pick.valid_votes or 0)
    return Decision(
        winner=winner, runner_up=runner, total_votes=total,
        valid_votes=pick.valid_votes, registered_voters=pick.registered_voters,
        accredited_voters=pick.accredited_voters, parties=dict(pick.parties),
        chosen_transcription_id=pick.id, method="stub:most-recent-with-figures",
    )
# --------------------------------------------------------------------------- #


def _load_submissions(db: Session, year: str, election: str | None):
    """{(pu_code, election_type): [Submission, ...]} for the given year."""
    q = select(SheetTranscription).where(SheetTranscription.year == year)
    if election:
        q = q.where(SheetTranscription.election_type == election)
    trs = db.scalars(q).all()
    parties_by_tr: dict[int, dict[str, int]] = defaultdict(dict)
    if trs:
        for tp in db.scalars(select(TranscriptionParty).where(
                TranscriptionParty.transcription_id.in_([t.id for t in trs]))).all():
            if tp.votes is not None:
                parties_by_tr[tp.transcription_id][tp.party] = tp.votes
    out: dict[tuple[str, str], list[Submission]] = defaultdict(list)
    for t in trs:
        out[(t.pu_code, t.election_type)].append(Submission(
            id=t.id, source=t.source, method=t.method, created_at=t.created_at,
            registered_voters=t.registered_voters, accredited_voters=t.accredited_voters,
            valid_votes=t.valid_votes, parties=parties_by_tr.get(t.id, {}),
        ))
    return out


def _pu_geo(db: Session):
    """pu_code -> (state_geo, lga_id, ward_code) from the polling_units table."""
    return {
        p.pu_code: (p.state_geo, p.lga_id, p.ward_code)
        for p in db.scalars(select(PollingUnit)).all()
    }


def _winner_runner(parties) -> tuple[str, str]:
    """Accepts a {party: votes} dict OR a list of (party, votes) pairs."""
    pairs = parties.items() if isinstance(parties, dict) else parties
    ranked = sorted(((p, v) for p, v in pairs if v), key=lambda x: x[1], reverse=True)
    return (ranked[0][0] if ranked else "", ranked[1][0] if len(ranked) > 1 else "")


def run(year: str, election: str | None, commit: bool) -> None:
    db = SessionLocal() if SessionLocal else None
    if db is None:
        print("DATABASE_URL not set — aborting.")
        return
    try:
        subs = _load_submissions(db, year, election)
        geo = _pu_geo(db)
        if not subs:
            print(f"No transcriptions found for year={year}"
                  f"{'/' + election if election else ''}. Nothing to do.")
            return

        # 1) choose a definitive per (pu, election)
        decisions: dict[tuple[str, str], Decision] = {}
        for key, slist in subs.items():
            d = choose(slist)
            if d is not None:
                decisions[key] = d
        print(f"Polling units with a chosen definitive: {len(decisions)} "
              f"(from {len(subs)} pu×election groups)")

        # accumulate rollups: {(geo_key, election_type): {party: votes}}
        ward_acc: dict = defaultdict(lambda: defaultdict(int))
        lga_acc: dict = defaultdict(lambda: defaultdict(int))
        state_acc: dict = defaultdict(lambda: defaultdict(int))
        ward_meta: dict = {}   # ward_code -> (state_geo, lga_id)

        for (pu_code, et), d in decisions.items():
            sgeo, lga_id, ward_code = geo.get(pu_code, (None, None, ""))
            for party, votes in d.parties.items():
                if ward_code:
                    ward_acc[(ward_code, et)][party] += votes
                if lga_id is not None:
                    lga_acc[(lga_id, et)][party] += votes
                if sgeo is not None:
                    state_acc[(sgeo, et)][party] += votes
            if ward_code:
                ward_meta[ward_code] = (sgeo, lga_id)

        n_ward = len(ward_acc)
        n_lga = len(lga_acc)
        n_state = len(state_acc)
        print(f"Rollups computed: {n_ward} ward, {n_lga} LGA, {n_state} state "
              "(source='rolled_up')")

        if not commit:
            # show a small sample and stop
            for key, d in list(decisions.items())[:5]:
                print(f"  PU {key[0]} [{key[1]}] -> winner={d.winner} total={d.total_votes} "
                      f"parties={d.parties} (from transcription {d.chosen_transcription_id})")
            print("\nDRY RUN — no writes. Re-run with --commit to persist.")
            return

        # 2) write definitive PU results (replace this year/election's rolled_up set)
        _replace_pu_results(db, year, election, decisions, geo)
        # 3) write rollups (replace this year/election's rolled_up set at each level)
        _replace_ward(db, year, election, ward_acc, ward_meta)
        _replace_lga(db, year, election, lga_acc, db)
        _replace_state(db, year, election, state_acc)
        db.commit()
        print("Committed.")
    finally:
        db.close()


def _del_rolled(db: Session, model, party_model, fk_attr, year, election):
    """Delete rolled_up rows (+ their party children) for this year/election so the
    script is re-runnable. Never touches source in ('declared','official')."""
    q = select(model.id).where(model.year == year, model.source == "rolled_up")
    if election:
        q = q.where(model.election_type == election)
    ids = [i for (i,) in db.execute(q).all()]
    if ids:
        db.execute(delete(party_model).where(getattr(party_model, fk_attr).in_(ids)))
        db.execute(delete(model).where(model.id.in_(ids)))


def _replace_pu_results(db, year, election, decisions, geo):
    _del_rolled(db, PuResult, PuResultParty, "pu_result_id", year, election)
    for (pu_code, et), d in decisions.items():
        sgeo, lga_id, ward_code = geo.get(pu_code, (None, None, ""))
        r = PuResult(
            pu_code=pu_code, election_type=et, year=year, state_geo=sgeo, lga_id=lga_id,
            ward_code=ward_code, winner=d.winner, runner_up=d.runner_up,
            total_votes=d.total_votes, valid_votes=d.valid_votes,
            registered_voters=d.registered_voters, accredited_voters=d.accredited_voters,
            source="rolled_up", chosen_transcription_id=d.chosen_transcription_id, method=d.method,
        )
        db.add(r); db.flush()
        for party, votes in d.parties.items():
            db.add(PuResultParty(pu_result_id=r.id, party=party, votes=votes))


def _replace_ward(db, year, election, ward_acc, ward_meta):
    _del_rolled(db, WardResultV, WardResultParty, "ward_result_id", year, election)
    for (ward_code, et), parties in ward_acc.items():
        parties = {p: v for p, v in parties.items()}
        winner, runner = _winner_runner(parties)
        sgeo, lga_id = ward_meta.get(ward_code, (None, None))
        r = WardResultV(ward_code=ward_code, lga_id=lga_id, election_type=et, year=year,
                        state_geo=sgeo, winner=winner, runner_up=runner,
                        total_votes=sum(parties.values()), source="rolled_up")
        db.add(r); db.flush()
        for party, votes in parties.items():
            db.add(WardResultParty(ward_result_id=r.id, party=party, votes=votes))


def _replace_lga(db, year, election, lga_acc, _db):
    _del_rolled(db, LgaResultV, LgaResultParty, "lga_result_id", year, election)
    lga_names = {l.id: l.name for l in db.scalars(select(Lga)).all()}
    for (lga_id, et), parties in lga_acc.items():
        parties = {p: v for p, v in parties.items()}
        winner, runner = _winner_runner(parties)
        r = LgaResultV(lga_id=lga_id, lga=lga_names.get(lga_id, ""), election_type=et, year=year,
                       winner=winner, runner_up=runner, total_votes=sum(parties.values()),
                       source="rolled_up")
        db.add(r); db.flush()
        for party, votes in parties.items():
            db.add(LgaResultParty(lga_result_id=r.id, party=party, votes=votes))


def _replace_state(db, year, election, state_acc):
    _del_rolled(db, StateResultV, StateResultParty, "state_result_id", year, election)
    for (sgeo, et), parties in state_acc.items():
        parties = {p: v for p, v in parties.items()}
        winner, runner = _winner_runner(parties)
        r = StateResultV(state_geo=sgeo, election_type=et, year=year, winner=winner,
                         runner_up=runner, total_votes=sum(parties.values()), source="rolled_up")
        db.add(r); db.flush()
        for party, votes in parties.items():
            db.add(StateResultParty(state_result_id=r.id, party=party, votes=votes))


# --------------------------------------------------------------------------- #
# Import the archived legacy results into the unified tables (source='official')
# --------------------------------------------------------------------------- #
def _clear_official(db: Session, model, party_model, fk_attr, state_geo=None) -> None:
    """Wipe prior source='official' rows (+ children) so the import is re-runnable.
    When state_geo is given, only that state's rows are removed (other states kept)."""
    q = select(model.id).where(model.source == "official")
    if state_geo is not None:
        q = q.where(model.state_geo == state_geo)
    ids = [i for (i,) in db.execute(q).all()]
    if ids:
        db.execute(delete(party_model).where(getattr(party_model, fk_attr).in_(ids)))
        db.execute(delete(model).where(model.id.in_(ids)))


def import_from_archive(commit: bool, state_geo=None) -> None:
    """Read the *_archive tables (+ polling_units.votes_*) and load them into the unified
    pu_results / *_result_v tables as source='official'. This is how we populate the new
    structure from the preserved legacy data. When state_geo is given, only that state is
    imported (and only that state's existing official rows are replaced). Dry-run unless
    --commit."""
    db = SessionLocal() if SessionLocal else None
    if db is None:
        print("DATABASE_URL not set — aborting.")
        return

    def _sfilter(q, model):
        return q.where(model.state_geo == state_geo) if state_geo is not None else q

    try:
        scope = f" (state_geo={state_geo})" if state_geo else " (ALL states)"
        # counts first (dry-run visibility)
        n_pu = db.scalar(_sfilter(select(func_count()).select_from(PollingUnit), PollingUnit))
        n_ward = db.scalar(_sfilter(select(func_count()).select_from(WardResult), WardResult))
        n_lga = db.scalar(_sfilter(select(func_count()).select_from(LgaPartyResult), LgaPartyResult))
        n_state = db.scalar(_sfilter(select(func_count()).select_from(StatePresidential), StatePresidential))
        print(f"Archive rows{scope}: polling_units={n_pu}, ward_results_archive={n_ward}, "
              f"lga_party_results_archive={n_lga}, state_presidential_archive={n_state}")
        if not commit:
            print("\nDRY RUN — no writes. Re-run with --commit to import into the unified tables.")
            return

        # 1) polling_units.votes_* -> pu_results (presidential 2023). Bulk for speed
        # (there are ~177k polling units nationwide).
        _clear_official(db, PuResult, PuResultParty, "pu_result_id", state_geo)
        pu_rows, pu_party_src = [], []  # parent mappings; (pu_code, [(party, votes)])
        for p in db.scalars(_sfilter(select(PollingUnit), PollingUnit)).all():
            parties = [(k, v) for k, v in (("APC", p.votes_apc), ("LP", p.votes_lp),
                                           ("PDP", p.votes_pdp), ("NNPP", p.votes_nnpp)) if v is not None]
            if not parties and p.known_votes is None:
                continue
            winner = p.winner or _winner_runner(parties)[0]
            runner = p.runner_up or _winner_runner(parties)[1]
            total = p.known_votes if p.known_votes is not None else sum(v for _, v in parties)
            pu_rows.append({"pu_code": p.pu_code, "election_type": "presidential", "year": "2023",
                            "state_geo": p.state_geo, "lga_id": p.lga_id, "ward_code": p.ward_code,
                            "winner": winner, "runner_up": runner, "total_votes": total,
                            "registered_voters": p.registered_voters, "source": "official", "method": "inec"})
            pu_party_src.append((p.pu_code, parties))
        pu_written = len(pu_rows)
        if pu_rows:
            db.bulk_insert_mappings(PuResult, pu_rows)
            db.flush()
            id_by_code = dict(db.execute(
                select(PuResult.pu_code, PuResult.id).where(PuResult.source == "official")).all())
            party_rows = [
                {"pu_result_id": id_by_code[code], "party": party, "votes": votes or 0}
                for code, parties in pu_party_src for party, votes in parties if code in id_by_code
            ]
            db.bulk_insert_mappings(PuResultParty, party_rows)
            db.flush()

        # 2) ward_results_archive -> ward_result_v
        _clear_official(db, WardResultV, WardResultParty, "ward_result_id", state_geo)
        for w in db.scalars(_sfilter(select(WardResult), WardResult)).all():
            r = WardResultV(ward_code=w.ward_code, ward=w.ward, lga_id=w.lga_id,
                            election_type="presidential", year="2023", state_geo=w.state_geo,
                            winner=w.winner, runner_up=w.runner_up, total_votes=w.total_votes,
                            source="official")
            db.add(r); db.flush()
            for party, votes in (("APC", w.votes_apc), ("LP", w.votes_lp), ("PDP", w.votes_pdp), ("NNPP", w.votes_nnpp)):
                db.add(WardResultParty(ward_result_id=r.id, party=party, votes=votes or 0))

        # 3) lga_party_results_archive -> lga_result_v (presidential + governor)
        _clear_official(db, LgaResultV, LgaResultParty, "lga_result_id", state_geo)
        groups: dict = {}
        for x in db.scalars(_sfilter(select(LgaPartyResult), LgaPartyResult)).all():
            groups.setdefault((x.election_type, x.year, x.state_geo, x.lga_id, x.lga), []).append((x.party, x.votes or 0))
        for (et, year, sgeo, lga_id, lga), parties in groups.items():
            winner, runner = _winner_runner(parties)
            r = LgaResultV(lga_id=lga_id, lga=lga, election_type=et, year=year, state_geo=sgeo,
                           winner=winner, runner_up=runner, total_votes=sum(v for _, v in parties),
                           source="official")
            db.add(r); db.flush()
            for party, votes in parties:
                db.add(LgaResultParty(lga_result_id=r.id, party=party, votes=votes))

        # 4) state_presidential_archive -> state_result_v
        _clear_official(db, StateResultV, StateResultParty, "state_result_id", state_geo)
        for s in db.scalars(_sfilter(select(StatePresidential), StatePresidential)).all():
            parts = [("APC", s.apc or 0), ("PDP", s.pdp or 0), ("LP", s.lp or 0),
                     ("NNPP", s.nnpp or 0), ("Others", s.others or 0)]
            winner = s.winner or _winner_runner(parts)[0]
            _, runner = _winner_runner(parts)
            r = StateResultV(state=s.state, state_geo=s.state_geo, election_type="presidential",
                             year=str(s.year), winner=winner, runner_up=runner,
                             total_votes=s.total_votes or sum(v for _, v in parts), source="official")
            db.add(r); db.flush()
            for party, votes in parts:
                if votes:
                    db.add(StateResultParty(state_result_id=r.id, party=party, votes=votes))

        db.commit()
        print(f"Imported: {pu_written} pu_results, ward/lga/state results from archive (source='official'). Committed.")
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", default="2023", help="election year to process (default 2023)")
    ap.add_argument("--election", default=None,
                    help="limit to one office (presidential|governor|senate|house); default all")
    ap.add_argument("--from-archive", action="store_true",
                    help="import the archived legacy results into the unified tables (source='official') "
                         "instead of running the transcription picker")
    ap.add_argument("--state", default=None,
                    help="limit --from-archive to one state's geo id (e.g. nga_3 for Akwa Ibom); "
                         "only that state's official rows are replaced")
    ap.add_argument("--commit", action="store_true",
                    help="actually write (default is a dry run that writes nothing)")
    args = ap.parse_args()
    if getattr(args, "from_archive", False):
        import_from_archive(args.commit, state_geo=args.state)
    else:
        run(args.year, args.election, args.commit)


if __name__ == "__main__":
    main()
