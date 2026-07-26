#!/usr/bin/env python
"""Deduct confidence from evidence readings that fail a quality rule, with an audit trail.

RULE (minor_party_over_2000): for 2023 PRESIDENTIAL evidence, if a MINOR party — anything
other than LP / APC / PDP / NNPP — is recorded with more than 2000 votes, that reading is
almost certainly an OCR misread (a real minor party never polls thousands at one PU). We
subtract 50 from that evidence row's confidence and record WHY in evidence_penalties (the
polling unit, the offending party + figure, the points removed).

Idempotent: this rule first RESTORES the points from its own prior penalties (so a re-run
doesn't stack deductions), deletes those penalty rows, then re-applies from scratch. Only
this rule's penalties are touched; other rules' penalties are left alone.

Run LOCALLY against $DATABASE_URL. Dry-run prints what it WOULD do; --commit writes.

    python -m scripts.penalize_evidence            # dry run
    python -m scripts.penalize_evidence --commit   # apply
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select, text, update  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Evidence, EvidencePenalty  # noqa: E402

RULE = "minor_party_over_2000"
MAJOR = ("LP", "APC", "PDP", "NNPP")
THRESHOLD = 2000
POINTS = 50
ELECTION = "presidential"
YEAR = "2023"


def _offenders(db):
    """Rows to penalize: {evidence_id: (pu_code, [(party, votes), ...])} — every 2023
    presidential evidence row that has a minor party over the threshold. A row is listed
    once with ALL its offending parties (each is a separate penalty record)."""
    # MAJOR is a fixed set of literals, so inline it (psycopg can't bind a tuple to IN).
    major_sql = ", ".join(f"'{p}'" for p in MAJOR)
    q = text(f"""
        SELECT e.id, e.pu_code, ep.party, ep.votes
        FROM evidence e
        JOIN evidence_parties ep ON ep.evidence_id = e.id
        WHERE e.election_type = :et AND e.year = :yr
          AND ep.party NOT IN ({major_sql})
          AND ep.votes > :thr
        ORDER BY e.id, ep.votes DESC
    """).bindparams(et=ELECTION, yr=YEAR, thr=THRESHOLD)
    out: dict[int, tuple] = {}
    for eid, pu, party, votes in db.execute(q).all():
        entry = out.setdefault(eid, (pu, []))
        entry[1].append((party, int(votes)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="apply (default: dry run)")
    args = ap.parse_args()

    db = SessionLocal() if SessionLocal else None
    if db is None:
        sys.exit("DATABASE_URL not set — aborting.")
    try:
        offenders = _offenders(db)
        n_rows = len(offenders)
        n_penalties = sum(len(v[1]) for v in offenders.values())
        print(f"Rule: {RULE}  (minor party not in {MAJOR}, > {THRESHOLD} votes, "
              f"{ELECTION} {YEAR})")
        print(f"Evidence rows to penalize: {n_rows:,}  ({n_penalties:,} offending party figures, "
              f"-{POINTS} conf per row)")
        prior = db.execute(text(
            "SELECT count(*), COALESCE(SUM(points),0) FROM evidence_penalties WHERE rule=:r"),
            {"r": RULE}).one()
        print(f"Prior {RULE} penalties on record (will be reset first): {prior[0]:,} "
              f"({prior[1]:,} points)")

        if not args.commit:
            for eid, (pu, parties) in list(offenders.items())[:6]:
                worst = ", ".join(f"{p}={v}" for p, v in parties)
                print(f"  e.g. evidence {eid} [{pu}] -> {worst}  (-{POINTS})")
            print("\nDRY RUN — no writes. Re-run with --commit.")
            return

        # 1) restore points from this rule's prior penalties, then delete them (idempotent).
        # Add back exactly what this rule removed per evidence row, capped at 100.
        print("\nResetting prior penalties for this rule...")
        db.execute(text("""
            UPDATE evidence e
               SET confidence = LEAST(100, COALESCE(e.confidence,0) + agg.pts)
              FROM (SELECT evidence_id, SUM(points) pts FROM evidence_penalties
                    WHERE rule = :r GROUP BY evidence_id) agg
             WHERE agg.evidence_id = e.id
        """), {"r": RULE})
        db.execute(delete(EvidencePenalty).where(EvidencePenalty.rule == RULE))
        db.flush()

        # 2) apply the deduction ONCE per evidence row (a row over the threshold on several
        # minor parties still loses POINTS once), and record one penalty per offending party.
        print(f"Applying -{POINTS} to {n_rows:,} evidence rows...")
        eids = list(offenders.keys())
        for i in range(0, len(eids), 10000):
            chunk = eids[i:i + 10000]
            db.execute(update(Evidence).where(Evidence.id.in_(chunk)).values(
                confidence=text(f"GREATEST(0, COALESCE(confidence,0) - {POINTS})")))
        db.flush()

        # 3) record the audit rows (one per offending party figure)
        pen_maps = []
        for eid, (pu, parties) in offenders.items():
            for party, votes in parties:
                pen_maps.append({
                    "evidence_id": eid, "pu_code": pu, "election_type": ELECTION, "year": YEAR,
                    "rule": RULE, "party": party, "votes": votes, "points": POINTS,
                    "reason": (f"{party} recorded {votes:,} votes — a minor party "
                               f"(not LP/APC/PDP/NNPP) over {THRESHOLD:,} is almost certainly "
                               f"an OCR misread; confidence reduced by {POINTS}."),
                })
        db.bulk_insert_mappings(EvidencePenalty, pen_maps)
        db.commit()
        print(f"Recorded {len(pen_maps):,} penalty rows. Done.")

        # distribution after
        print("\nConfidence distribution of penalized evidence rows (after):")
        rows = db.execute(text("""
            SELECT e.confidence, count(*) FROM evidence e
            WHERE e.id IN (SELECT DISTINCT evidence_id FROM evidence_penalties WHERE rule=:r)
            GROUP BY e.confidence ORDER BY e.confidence
        """), {"r": RULE}).all()
        for conf, n in rows:
            print(f"  confidence {conf}: {n:,}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
