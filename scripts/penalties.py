#!/usr/bin/env python
"""Confidence PENALTY rules for evidence, with a full audit trail.

Some evidence readings are demonstrably wrong (OCR misreads). Instead of silently
lowering a score, every deduction is a RULE that:
  * finds the offending evidence rows,
  * subtracts points from evidence.confidence,
  * records one row per reason in evidence_penalties (which PU, why, party+votes, points).

Each rule is IDEMPOTENT and SELF-CONTAINED: before applying, it restores the points from
its OWN prior penalties and deletes them, then re-applies. So running a rule twice is a
no-op, and running one rule never disturbs another rule's penalties.

Rules (all: 2023 presidential):
  minor_party_over_2000  — a minor party (not APC/LP/PDP/NNPP) recorded > 2000 votes.  -50
  all_majors_zero_minors — APC = PDP = LP = 0 while 2+ minor parties (not APC/PDP/LP/    -50
                           NNPP) each score > 100. A sheet where the three biggest parties
                           are blank but small parties aren't is a mis-aligned read.

Run LOCALLY against $DATABASE_URL. Choose rules with --rules (default: all). Dry-run
prints what it WOULD do; --commit writes.

    python -m scripts.penalties                          # dry run, all rules
    python -m scripts.penalties --rules all_majors_zero_minors --commit
    python -m scripts.penalties --commit                 # apply all rules
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, text, update  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Evidence, EvidencePenalty  # noqa: E402

ELECTION = "presidential"
YEAR = "2023"
POINTS = 50


# --------------------------------------------------------------------------- #
# Rule finders. Each returns {evidence_id: (pu_code, [(party, votes, reason), ...])}.
# One tuple per party generates one penalty record; the evidence row is docked POINTS once.
# --------------------------------------------------------------------------- #
def find_minor_party_over_2000(db) -> dict:
    """A minor party (not APC/LP/PDP/NNPP) with more than 2000 votes — an OCR misread."""
    majors = "'LP','APC','PDP','NNPP'"
    q = text(f"""
        SELECT e.id, e.pu_code, ep.party, ep.votes
        FROM evidence e JOIN evidence_parties ep ON ep.evidence_id = e.id
        WHERE e.election_type = :et AND e.year = :yr
          AND ep.party NOT IN ({majors}) AND ep.votes > 2000
        ORDER BY e.id, ep.votes DESC
    """).bindparams(et=ELECTION, yr=YEAR)
    out: dict[int, tuple] = {}
    for eid, pu, party, votes in db.execute(q).all():
        reason = (f"{party} recorded {int(votes):,} votes — a minor party (not "
                  f"LP/APC/PDP/NNPP) over 2,000 is almost certainly an OCR misread.")
        out.setdefault(eid, (pu, []))[1].append((party, int(votes), reason))
    return out


def find_all_majors_zero_minors(db) -> dict:
    """APC = PDP = LP = 0 while 2+ minor parties (not APC/PDP/LP/NNPP) each score > 100.
    A sheet where the three biggest parties are all blank/zero but small parties are not is
    a mis-aligned read (the figures landed on the wrong rows)."""
    # aggregate per evidence row; count qualifying minors and grab the majors' figures
    q = text("""
        WITH ev AS (
          SELECT e.id, e.pu_code,
            COALESCE(MAX(ep.votes) FILTER (WHERE ep.party='APC'),0) AS apc,
            COALESCE(MAX(ep.votes) FILTER (WHERE ep.party='PDP'),0) AS pdp,
            COALESCE(MAX(ep.votes) FILTER (WHERE ep.party='LP'),0)  AS lp,
            COUNT(*) FILTER (WHERE ep.party NOT IN ('APC','PDP','LP','NNPP')
                             AND ep.votes > 100) AS minor_over_100
          FROM evidence e JOIN evidence_parties ep ON ep.evidence_id = e.id
          WHERE e.election_type = :et AND e.year = :yr
          GROUP BY e.id, e.pu_code
        )
        SELECT id, pu_code, minor_over_100 FROM ev
        WHERE apc = 0 AND pdp = 0 AND lp = 0 AND minor_over_100 >= 2
    """).bindparams(et=ELECTION, yr=YEAR)
    hits = {r[0]: (r[1], int(r[2])) for r in db.execute(q).all()}
    if not hits:
        return {}
    # pull the qualifying minor parties for each hit, for the audit records
    ids = list(hits.keys())
    out: dict[int, tuple] = {eid: (pu, []) for eid, (pu, _n) in hits.items()}
    for i in range(0, len(ids), 20000):
        chunk = ids[i:i + 20000]
        rows = db.execute(text("""
            SELECT ep.evidence_id, ep.party, ep.votes
            FROM evidence_parties ep
            WHERE ep.evidence_id = ANY(:ids)
              AND ep.party NOT IN ('APC','PDP','LP','NNPP') AND ep.votes > 100
            ORDER BY ep.evidence_id, ep.votes DESC
        """).bindparams(ids=chunk))
        for eid, party, votes in rows.all():
            n = hits[eid][1]
            reason = (f"{party} scored {int(votes):,} while APC, PDP and LP all read 0 "
                      f"({n} minor parties over 100) — a mis-aligned/misread sheet.")
            out[eid][1].append((party, int(votes), reason))
    return out


RULES = {
    "minor_party_over_2000": find_minor_party_over_2000,
    "all_majors_zero_minors": find_all_majors_zero_minors,
}


# --------------------------------------------------------------------------- #
def _reset_rule(db, rule: str) -> None:
    """Restore points from this rule's prior penalties, then delete them (idempotent)."""
    db.execute(text("""
        UPDATE evidence e
           SET confidence = LEAST(100, COALESCE(e.confidence,0) + agg.pts)
          FROM (SELECT evidence_id, SUM(points) pts FROM evidence_penalties
                WHERE rule = :r GROUP BY evidence_id) agg
         WHERE agg.evidence_id = e.id
    """), {"r": rule})
    db.execute(delete(EvidencePenalty).where(EvidencePenalty.rule == rule))
    db.flush()


def _apply_rule(db, rule: str, hits: dict, commit: bool) -> int:
    """Dock POINTS once per hit evidence row and record one penalty per offending party.
    Returns the number of evidence rows affected."""
    n_rows = len(hits)
    n_pen = sum(len(v[1]) for v in hits.values())
    prior = db.execute(text(
        "SELECT count(*), COALESCE(SUM(points),0) FROM evidence_penalties WHERE rule=:r"),
        {"r": rule}).one()
    print(f"[{rule}] evidence rows to penalize: {n_rows:,} "
          f"({n_pen:,} offending party figures, -{POINTS} each)")
    print(f"[{rule}] prior penalties on record (reset first): {prior[0]:,} ({prior[1]:,} pts)")
    for eid, (pu, parties) in list(hits.items())[:4]:
        worst = ", ".join(f"{p}={v}" for p, v, _ in parties[:6])
        print(f"    e.g. evidence {eid} [{pu}] -> {worst}  (-{POINTS})")
    if not commit:
        return n_rows

    _reset_rule(db, rule)
    eids = list(hits.keys())
    for i in range(0, len(eids), 10000):
        chunk = eids[i:i + 10000]
        db.execute(update(Evidence).where(Evidence.id.in_(chunk)).values(
            confidence=text(f"GREATEST(0, COALESCE(confidence,0) - {POINTS})")))
    db.flush()
    pen_maps = []
    for eid, (pu, parties) in hits.items():
        for party, votes, reason in parties:
            pen_maps.append({
                "evidence_id": eid, "pu_code": pu, "election_type": ELECTION, "year": YEAR,
                "rule": rule, "party": party, "votes": votes, "points": POINTS, "reason": reason,
            })
    if pen_maps:
        db.bulk_insert_mappings(EvidencePenalty, pen_maps)
    db.commit()
    print(f"[{rule}] applied. {n_rows:,} evidence rows docked, {len(pen_maps):,} penalty rows recorded.")
    return n_rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rules", default="all",
                    help="comma-separated rule names to run (default: all). "
                         f"Available: {', '.join(RULES)}")
    ap.add_argument("--commit", action="store_true", help="apply (default: dry run)")
    args = ap.parse_args()

    if args.rules == "all":
        chosen = list(RULES)
    else:
        chosen = [r.strip() for r in args.rules.split(",") if r.strip()]
        bad = [r for r in chosen if r not in RULES]
        if bad:
            sys.exit(f"unknown rule(s): {', '.join(bad)}. Available: {', '.join(RULES)}")

    db = SessionLocal() if SessionLocal else None
    if db is None:
        sys.exit("DATABASE_URL not set — aborting.")
    try:
        print(f"Running rules: {', '.join(chosen)}  ({ELECTION} {YEAR})")
        print(f"Mode: {'COMMIT' if args.commit else 'DRY RUN'}\n")
        totals = {}
        for rule in chosen:
            hits = RULES[rule](db)
            totals[rule] = _apply_rule(db, rule, hits, args.commit)
            print()
        print("=== SUMMARY ===")
        for rule, n in totals.items():
            print(f"  {rule}: {n:,} evidence rows affected")
        if not args.commit:
            print("\nDRY RUN — no writes. Re-run with --commit.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
