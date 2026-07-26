#!/usr/bin/env python
"""Stamp our qwen LLM evidence rows with a 0-100 confidence score from sheet quality.

Each qwen transcription (evidence.kind='llm', source LIKE 'LLM (qwen%') gets the same
score its polling-unit result would (see app/confidence.py), computed from the matching
pu_sheet:
  0   the sheet was auto-voided as an inflated misread (a kind='correction' row exists)
  10  blurry / illegible
  20  missing sheet location (no URL, or sheet_status no_sheet/dead, or no sheet row)
  85  model 'unsure'
  100 clean valid sheet

Set-based SQL so it scores all ~350k qwen rows in seconds. Only qwen rows are touched;
other evidence kinds (2023_transcription, correction, human, crowd) are left null unless
you extend this. Run LOCALLY against $DATABASE_URL. Dry-run prints the distribution;
--commit applies it. Idempotent — re-running recomputes from current sheet state.

    python -m scripts.stamp_evidence_confidence            # dry run
    python -m scripts.stamp_evidence_confidence --commit   # apply
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app import confidence as C  # noqa: E402

# Which evidence rows we stamp: our qwen LLM transcriptions.
_QWEN_WHERE = "e.kind = 'llm' AND e.source LIKE 'LLM (qwen%'"

# Score each qwen evidence row from its matching pu_sheet (same pu_code+office+year) and
# whether that (pu, office, year) has a correction row (auto-voided inflated misread).
# Mirrors app/confidence.score_from_sheet exactly.
_UPDATE_SQL = f"""
WITH scored AS (
    SELECT e.id,
           CASE
               WHEN cor.pu_code IS NOT NULL THEN {C.SCORE_INFLATED}
               WHEN LOWER(COALESCE(s.legibility,'')) IN ('illegible','blurry')
                    OR LOWER(COALESCE(s.status,'')) = 'blurry' THEN {C.SCORE_BLURRY}
               WHEN s.pu_code IS NULL
                    OR COALESCE(s.sheet_url,'') = ''
                    OR LOWER(COALESCE(s.sheet_status,'')) IN ('no_sheet','dead','') THEN {C.SCORE_MISSING_SHEET}
               WHEN LOWER(COALESCE(s.status,'')) = 'unsure' THEN {C.SCORE_UNSURE}
               ELSE {C.SCORE_VALID}
           END AS score
    FROM evidence e
    LEFT JOIN pu_sheets s
           ON s.pu_code = e.pu_code
          AND s.election_type = e.election_type
          AND s.year = e.year
    LEFT JOIN (
        SELECT DISTINCT pu_code, election_type, year
        FROM evidence WHERE kind = 'correction'
    ) cor ON cor.pu_code = e.pu_code
         AND cor.election_type = e.election_type
         AND cor.year = e.year
    WHERE {_QWEN_WHERE}
)
UPDATE evidence e
   SET confidence = scored.score
  FROM scored
 WHERE scored.id = e.id
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="apply the update (default: dry run)")
    args = ap.parse_args()

    db = SessionLocal() if SessionLocal else None
    if db is None:
        sys.exit("DATABASE_URL not set — aborting.")
    try:
        total = db.execute(text(f"SELECT count(*) FROM evidence e WHERE {_QWEN_WHERE}")).scalar()
        print(f"qwen LLM evidence rows: {total:,}")
        print(f"score rules: inflated={C.SCORE_INFLATED} blurry={C.SCORE_BLURRY} "
              f"missing_sheet={C.SCORE_MISSING_SHEET} unsure={C.SCORE_UNSURE} valid={C.SCORE_VALID}")

        # scoring CTE reused as a SELECT for the preview
        sel = _UPDATE_SQL[_UPDATE_SQL.index("WITH"):_UPDATE_SQL.index("UPDATE")]
        sel += "SELECT score, count(*) FROM scored GROUP BY score ORDER BY score"

        if not args.commit:
            print("\nDRY RUN — distribution WITHOUT writing:")
            for score, n in db.execute(text(sel)).all():
                print(f"  score {score:>3}  ({C.band(score):<6})  {n:,}")
            print("\nNo writes. Re-run with --commit to apply.")
            return

        print("\nStamping qwen evidence confidence...")
        res = db.execute(text(_UPDATE_SQL))
        db.commit()
        print(f"Updated {res.rowcount:,} evidence rows.")
        print("\nResulting distribution (qwen rows):")
        for score, band, n in db.execute(text(
                f"SELECT confidence, CASE WHEN confidence>=80 THEN 'high' "
                f"WHEN confidence>=50 THEN 'medium' ELSE 'low' END, count(*) "
                f"FROM evidence e WHERE {_QWEN_WHERE} GROUP BY 1,2 ORDER BY 1")).all():
            print(f"  score {int(score) if score is not None else 'null':>4}  {band or '-':<7} {n:,}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
