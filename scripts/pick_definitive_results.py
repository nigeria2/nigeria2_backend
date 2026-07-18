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
    Evidence, EvidenceParty,
    WardEvidence, WardEvidenceParty,
    LgaEvidence, LgaEvidenceParty,
    StateEvidence, StateEvidenceParty,
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
    chosen_evidence_id: int | None = None
    method: str = "placeholder"


@dataclass
class EvidenceRow:
    """One piece of evidence flattened for the algorithm's convenience."""
    id: int
    kind: str                         # inec | llm | human | crowd
    source: str
    submitted_by: str
    submitted_by_id: int | None
    method: str
    created_at: object
    registered_voters: int | None
    accredited_voters: int | None
    valid_votes: int | None
    parties: dict[str, int]          # party -> votes (blank figures dropped)


def choose(evs: list[EvidenceRow]) -> Decision | None:
    """Choose the definitive result for ONE polling unit / election by weighing its
    EVIDENCE. Return None to leave the PU without a definitive result.

    ⚠️  PLACEHOLDER POLICY — REPLACE WITH THE REAL ALGORITHM (which should weigh evidence
    by kind and by the submitting user's trust). Current stub: prefer INEC evidence with
    party figures; else the most recent evidence with figures; else the most recent for a
    summary only.
    """
    if not evs:
        return None
    with_parties = [e for e in evs if e.parties]
    inec_with = [e for e in with_parties if e.kind == "inec"]
    if inec_with:
        pick = inec_with[0]
    elif with_parties:
        pick = max(with_parties, key=lambda e: (e.created_at is not None, e.created_at))
    else:
        pick = max(evs, key=lambda e: (e.created_at is not None, e.created_at))
    ranked = sorted(pick.parties.items(), key=lambda kv: kv[1], reverse=True)
    winner = ranked[0][0] if ranked else ""
    runner = ranked[1][0] if len(ranked) > 1 else ""
    total = sum(pick.parties.values()) if pick.parties else (pick.valid_votes or 0)
    return Decision(
        winner=winner, runner_up=runner, total_votes=total,
        valid_votes=pick.valid_votes, registered_voters=pick.registered_voters,
        accredited_voters=pick.accredited_voters, parties=dict(pick.parties),
        chosen_evidence_id=pick.id, method=f"stub:prefer-inec ({pick.kind})",
    )
# --------------------------------------------------------------------------- #


def _load_evidence(db: Session, year: str, election: str | None):
    """{(pu_code, election_type): [EvidenceRow, ...]} for the given year."""
    q = select(Evidence).where(Evidence.year == year)
    if election:
        q = q.where(Evidence.election_type == election)
    evs = db.scalars(q).all()
    parties_by_ev: dict[int, dict[str, int]] = defaultdict(dict)
    if evs:
        for ep in db.scalars(select(EvidenceParty).where(
                EvidenceParty.evidence_id.in_([e.id for e in evs]))).all():
            if ep.votes is not None:
                parties_by_ev[ep.evidence_id][ep.party] = ep.votes
    out: dict[tuple[str, str], list[EvidenceRow]] = defaultdict(list)
    for e in evs:
        out[(e.pu_code, e.election_type)].append(EvidenceRow(
            id=e.id, kind=e.kind, source=e.source, submitted_by=e.submitted_by,
            submitted_by_id=e.submitted_by_id, method=e.method, created_at=e.created_at,
            registered_voters=e.registered_voters, accredited_voters=e.accredited_voters,
            valid_votes=e.valid_votes, parties=parties_by_ev.get(e.id, {}),
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
        evidence = _load_evidence(db, year, election)
        geo = _pu_geo(db)
        if not evidence:
            print(f"No evidence found for year={year}"
                  f"{'/' + election if election else ''}. Nothing to do.")
            return

        # 1) choose a definitive per (pu, election) by weighing the evidence
        decisions: dict[tuple[str, str], Decision] = {}
        for key, elist in evidence.items():
            d = choose(elist)
            if d is not None:
                decisions[key] = d
        print(f"Polling units with a chosen definitive: {len(decisions)} "
              f"(from {len(evidence)} pu×election groups)")

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
                      f"parties={d.parties} (from evidence {d.chosen_evidence_id})")
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
    idq = select(model.id).where(model.year == year, model.source == "rolled_up")
    if election:
        idq = idq.where(model.election_type == election)
    db.execute(delete(party_model).where(getattr(party_model, fk_attr).in_(idq)))
    db.execute(delete(model).where(model.id.in_(idq)))


def _replace_pu_results(db, year, election, decisions, geo):
    _del_rolled(db, PuResult, PuResultParty, "pu_result_id", year, election)
    for (pu_code, et), d in decisions.items():
        sgeo, lga_id, ward_code = geo.get(pu_code, (None, None, ""))
        r = PuResult(
            pu_code=pu_code, election_type=et, year=year, state_geo=sgeo, lga_id=lga_id,
            ward_code=ward_code, winner=d.winner, runner_up=d.runner_up,
            total_votes=d.total_votes, valid_votes=d.valid_votes,
            registered_voters=d.registered_voters,
            source="rolled_up", method=d.method,
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
    When state_geo is given, only that state's rows are removed (other states kept).
    Uses a correlated subquery (NOT a Python id list) — an id list can blow past the
    driver's bind-parameter limit for 100k+ rows and silently fail to clear."""
    idq = select(model.id).where(model.source == "official")
    if state_geo is not None:
        idq = idq.where(model.state_geo == state_geo)
    db.execute(delete(party_model).where(getattr(party_model, fk_attr).in_(idq)))
    db.execute(delete(model).where(model.id.in_(idq)))


def _clear_evidence(db: Session, model, party_model, fk_attr, kind, state_geo=None) -> None:
    """Wipe prior evidence of one kind (+ children) for this scope, via subquery."""
    idq = select(model.id).where(model.kind == kind)
    if state_geo is not None:
        idq = idq.where(model.state_geo == state_geo)
    db.execute(delete(party_model).where(getattr(party_model, fk_attr).in_(idq)))
    db.execute(delete(model).where(model.id.in_(idq)))


def import_from_archive(commit: bool, state_geo=None, state_only=False) -> None:
    """Read the *_archive tables (+ polling_units.votes_*) and load them into the unified
    pu_results / *_result_v tables as source='official'. This is how we populate the new
    structure from the preserved legacy data. When state_geo is given, only that state is
    imported (and only that state's existing official rows are replaced). When state_only,
    ONLY the state-level-only archive (state_presidential_archive, e.g. 2019 + non-drilled
    2023 states) is loaded — skips the heavy 177k-PU rollup. Dry-run unless --commit."""
    db = SessionLocal() if SessionLocal else None
    if db is None:
        print("DATABASE_URL not set — aborting.")
        return

    if state_only:
        n_state = db.scalar(select(func_count()).select_from(StatePresidential))
        print(f"state_presidential_archive rows: {n_state}")
        if not commit:
            print("\nDRY RUN — no writes. Re-run with --commit.")
            db.close(); return
        n = _load_state_declared(db, state_geo)
        db.commit()
        print(f"Loaded {n} state-level results directly (declared). Committed.")
        db.close(); return

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

        # 1) polling_units.votes_* -> an INEC EVIDENCE row per unit, then derive a
        # pu_result pointing at it. Every result therefore has >=1 evidence row.
        # Bulk for speed (~177k units nationwide).
        _clear_official(db, PuResult, PuResultParty, "pu_result_id", state_geo)
        # clear prior 2023_transcription evidence for this scope so re-runs don't duplicate.
        # Subquery, not an id list (a 100k+ IN list blows the driver's parameter limit).
        eq = select(Evidence.id).where(Evidence.kind == "2023_transcription")
        if state_geo is not None:
            eq = eq.where(Evidence.state_geo == state_geo)
        db.execute(delete(EvidenceParty).where(EvidenceParty.evidence_id.in_(eq)))
        db.execute(delete(Evidence).where(Evidence.id.in_(eq)))

        units = []  # (pu_code, state_geo, lga_id, ward_code, winner, runner, total, reg, [(party,votes)])
        for p in db.scalars(_sfilter(select(PollingUnit), PollingUnit)).all():
            parties = [(k, v) for k, v in (("APC", p.votes_apc), ("LP", p.votes_lp),
                                           ("PDP", p.votes_pdp), ("NNPP", p.votes_nnpp)) if v is not None]
            if not parties and p.known_votes is None:
                continue
            winner = p.winner or _winner_runner(parties)[0]
            runner = p.runner_up or _winner_runner(parties)[1]
            total = p.known_votes if p.known_votes is not None else sum(v for _, v in parties)
            units.append((p.pu_code, p.state_geo, p.lga_id, p.ward_code, winner, runner,
                          total, p.registered_voters, parties))
        pu_written = len(units)
        if units:
            # 1a) one piece of evidence per unit (kind='2023_transcription'). Every entry is
            # a GUESS — no submitted_by (we are never sure who produced it), no "chosen".
            db.bulk_insert_mappings(Evidence, [
                {"pu_code": u[0], "election_type": "presidential", "year": "2023",
                 "state_geo": u[1], "kind": "2023_transcription", "source": "2023_transcription",
                 "method": "crosscheck", "valid_votes": u[6]}
                for u in units
            ])
            db.flush()
            ev_by_code = dict(db.execute(
                select(Evidence.pu_code, Evidence.id)
                .where(Evidence.kind == "2023_transcription")).all())
            db.bulk_insert_mappings(EvidenceParty, [
                {"evidence_id": ev_by_code[u[0]], "party": party, "votes": votes}
                for u in units for party, votes in u[8] if u[0] in ev_by_code
            ])
            # 1b) the unit result = a MERGE of the evidence. Today there is one entry, so the
            # merge is a copy of it. No chosen_evidence_id; method records that.
            db.bulk_insert_mappings(PuResult, [
                {"pu_code": u[0], "election_type": "presidential", "year": "2023",
                 "state_geo": u[1], "lga_id": u[2], "ward_code": u[3], "winner": u[4],
                 "runner_up": u[5], "total_votes": u[6], "registered_voters": u[7],
                 "source": "official", "method": "single-source"}
                for u in units
            ])
            db.flush()
            id_by_code = dict(db.execute(
                select(PuResult.pu_code, PuResult.id).where(PuResult.source == "official")).all())
            db.bulk_insert_mappings(PuResultParty, [
                {"pu_result_id": id_by_code[u[0]], "party": party, "votes": votes or 0}
                for u in units for party, votes in u[8] if u[0] in id_by_code
            ])
            db.flush()

        # 2-4) Roll up bottom-up. At each level we write a 'rollup' EVIDENCE row (the sum of
        # the level below is evidence for this level's score) plus the merged *_result_v.
        # Independent-source evidence (INEC-declared, etc.) is loaded separately when we
        # have it; today each level has just its rollup evidence, so result = that rollup.
        lga_names = {l.id: l.name for l in db.scalars(select(Lga)).all()}
        _rollup_ward(db, state_geo)
        _rollup_lga(db, state_geo, lga_names)
        _rollup_state(db, state_geo)
        # State-level-only archive data (e.g. 2019 presidential): no level below to roll up,
        # so load it directly as INDEPENDENT state evidence + the state result. This is the
        # top-down case — data that arrives at the state level from another source.
        n_direct = _load_state_declared(db, state_geo)

        db.commit()
        print(f"Imported: {pu_written} pu_results + INEC-sheet evidence; ward/lga/state rolled up; "
              f"{n_direct} state-level results loaded directly (declared). Committed.")
    finally:
        db.close()


def _agg_below(db, child_result, child_party, child_fk, group_cols, state_geo):
    """Sum a child *_result_v level per parent group + party. Returns
    {group_key_tuple: {party: votes}} where group_key_tuple = values of `group_cols`."""
    q = select(*group_cols, child_party.party, func_sum(child_party.votes)).join(
        child_party, getattr(child_party, child_fk) == child_result.id
    ).where(child_result.election_type == "presidential", child_result.year == "2023")
    if state_geo is not None:
        q = q.where(child_result.state_geo == state_geo)
    q = q.group_by(*group_cols, child_party.party)
    out: dict = {}
    for row in db.execute(q).all():
        *keys, party, votes = row
        out.setdefault(tuple(keys), {})[party] = int(votes or 0)
    return out


def func_sum(col):
    return _sa_func.sum(col)


def _rollup_ward(db, state_geo):
    """ward_evidence(rollup) + ward_result_v, summed from pu_results."""
    _clear_official(db, WardResultV, WardResultParty, "ward_result_id", state_geo)
    _clear_evidence(db, WardEvidence, WardEvidenceParty, "ward_evidence_id", "rollup", state_geo)
    agg = _agg_below(db, PuResult, PuResultParty, "pu_result_id",
                     (PuResult.ward_code, PuResult.state_geo, PuResult.lga_id), state_geo)
    for (ward_code, sgeo, lga_id), parties in agg.items():
        if not ward_code:
            continue
        winner, runner = _winner_runner(parties)
        total = sum(parties.values())
        ev = WardEvidence(ward_code=ward_code, election_type="presidential", year="2023",
                          state_geo=sgeo, kind="rollup", source="polling units",
                          method="sum-of-pu", total_votes=total)
        db.add(ev); db.flush()
        for p, v in parties.items():
            db.add(WardEvidenceParty(ward_evidence_id=ev.id, party=p, votes=v))
        r = WardResultV(ward_code=ward_code, lga_id=lga_id, election_type="presidential",
                        year="2023", state_geo=sgeo, winner=winner, runner_up=runner,
                        total_votes=total, source="official")
        db.add(r); db.flush()
        for p, v in parties.items():
            db.add(WardResultParty(ward_result_id=r.id, party=p, votes=v))


def _rollup_lga(db, state_geo, lga_names):
    """lga_evidence(rollup) + lga_result_v, summed from ward_result_v."""
    _clear_official(db, LgaResultV, LgaResultParty, "lga_result_id", state_geo)
    _clear_evidence(db, LgaEvidence, LgaEvidenceParty, "lga_evidence_id", "rollup", state_geo)
    agg = _agg_below(db, WardResultV, WardResultParty, "ward_result_id",
                     (WardResultV.lga_id, WardResultV.state_geo), state_geo)
    for (lga_id, sgeo), parties in agg.items():
        if lga_id is None:
            continue
        winner, runner = _winner_runner(parties)
        total = sum(parties.values())
        ev = LgaEvidence(lga_id=lga_id, election_type="presidential", year="2023",
                         state_geo=sgeo, kind="rollup", source="wards", method="sum-of-wards",
                         total_votes=total)
        db.add(ev); db.flush()
        for p, v in parties.items():
            db.add(LgaEvidenceParty(lga_evidence_id=ev.id, party=p, votes=v))
        r = LgaResultV(lga_id=lga_id, lga=lga_names.get(lga_id, ""), election_type="presidential",
                       year="2023", state_geo=sgeo, winner=winner, runner_up=runner,
                       total_votes=total, source="official")
        db.add(r); db.flush()
        for p, v in parties.items():
            db.add(LgaResultParty(lga_result_id=r.id, party=p, votes=v))


def _rollup_state(db, state_geo):
    """state_evidence(rollup) + state_result_v, summed from lga_result_v."""
    _clear_official(db, StateResultV, StateResultParty, "state_result_id", state_geo)
    _clear_evidence(db, StateEvidence, StateEvidenceParty, "state_evidence_id", "rollup", state_geo)
    agg = _agg_below(db, LgaResultV, LgaResultParty, "lga_result_id",
                     (LgaResultV.state_geo,), state_geo)
    from app import geo as _geo
    for (sgeo,), parties in agg.items():
        if sgeo is None:
            continue
        winner, runner = _winner_runner(parties)
        total = sum(parties.values())
        ev = StateEvidence(election_type="presidential", year="2023", state_geo=sgeo,
                           kind="rollup", source="LGAs", method="sum-of-lgas", total_votes=total)
        db.add(ev); db.flush()
        for p, v in parties.items():
            db.add(StateEvidenceParty(state_evidence_id=ev.id, party=p, votes=v))
        r = StateResultV(state=_geo.state_name(sgeo) or "", state_geo=sgeo,
                         election_type="presidential", year="2023", winner=winner,
                         runner_up=runner, total_votes=total, source="official")
        db.add(r); db.flush()
        for p, v in parties.items():
            db.add(StateResultParty(state_result_id=r.id, party=p, votes=v))


def _load_state_declared(db, state_geo) -> int:
    """Load state-level-only archive results (state_presidential_archive) directly, for any
    year — this is the top-down case (e.g. 2019 presidential) where there is no level below
    to roll up. These figures are collated aggregates with no result-sheet artifact behind
    them and mixed/unknown provenance, so they are recorded HONESTLY as a piece of evidence
    with kind='declared' / source='collated (provenance unknown)' — NOT as an INEC-declared
    number (we do not hold INEC's own declaration as a distinct source). Loaded ONLY for a
    (state, year) that has no rolled-up result already (so real rollups win)."""
    # clear both the honest 'declared' rows and any earlier mislabelled 'inec_declared' ones
    _clear_evidence(db, StateEvidence, StateEvidenceParty, "state_evidence_id", "declared", state_geo)
    _clear_evidence(db, StateEvidence, StateEvidenceParty, "state_evidence_id", "inec_declared", state_geo)
    # (state, year) pairs that have a genuine ROLLUP (kind='rollup') — those win; leave them.
    # (Must key off rollup EVIDENCE, not state_result_v.source='official' — the latter also
    #  covers our own declared loads, which would make every pair look "rolled" on a re-run.)
    rolled = {(sgeo, yr) for (sgeo, yr) in db.execute(
        select(StateEvidence.state_geo, StateEvidence.year).where(StateEvidence.kind == "rollup")).all()}
    n = 0
    q = select(StatePresidential)
    if state_geo is not None:
        q = q.where(StatePresidential.state_geo == state_geo)
    for s in db.scalars(q).all():
        yr = str(s.year)
        if (s.state_geo, yr) in rolled:
            continue  # a rollup exists for this state/year; leave it
        parts = [("APC", s.apc or 0), ("PDP", s.pdp or 0), ("LP", s.lp or 0),
                 ("NNPP", s.nnpp or 0), ("Others", s.others or 0)]
        parts = [(p, v) for p, v in parts if v]
        winner = s.winner or _winner_runner(parts)[0]
        _, runner = _winner_runner(parts)
        total = s.total_votes or sum(v for _, v in parts)
        # remove any prior official state result for this exact state/year first
        idq = select(StateResultV.id).where(
            StateResultV.state_geo == s.state_geo, StateResultV.year == yr,
            StateResultV.election_type == "presidential", StateResultV.source == "official")
        db.execute(delete(StateResultParty).where(StateResultParty.state_result_id.in_(idq)))
        db.execute(delete(StateResultV).where(StateResultV.id.in_(idq)))
        ev = StateEvidence(election_type="presidential", year=yr, state_geo=s.state_geo,
                           kind="declared", source="collated (provenance unknown)",
                           method="state-declared", total_votes=total)
        db.add(ev); db.flush()
        for p, v in parts:
            db.add(StateEvidenceParty(state_evidence_id=ev.id, party=p, votes=v))
        r = StateResultV(state=s.state, state_geo=s.state_geo, election_type="presidential",
                         year=yr, winner=winner, runner_up=runner, total_votes=total, source="official")
        db.add(r); db.flush()
        for p, v in parts:
            db.add(StateResultParty(state_result_id=r.id, party=p, votes=v))
        n += 1
    return n


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
    ap.add_argument("--state-only", action="store_true",
                    help="with --from-archive: load ONLY the state-level-only archive "
                         "(2019 + non-drilled 2023 state totals); skips the heavy PU rollup")
    ap.add_argument("--commit", action="store_true",
                    help="actually write (default is a dry run that writes nothing)")
    args = ap.parse_args()
    if getattr(args, "from_archive", False):
        import_from_archive(args.commit, state_geo=args.state, state_only=getattr(args, "state_only", False))
    else:
        run(args.year, args.election, args.commit)


if __name__ == "__main__":
    main()
