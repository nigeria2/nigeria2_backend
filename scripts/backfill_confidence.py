#!/usr/bin/env python
"""Backfill pu_results.confidence (0-100) + confidence_band from sheet quality.

The FIRST confidence signal is the quality of the result SHEET a unit's result came from:
  0   inflated/voided misread  (a kind='correction' evidence row voided the sheet)
  10  blurry / illegible sheet
  20  missing sheet location    (no sheet URL, or sheet_status no_sheet/dead, or no sheet row)
  85  model 'unsure'            (readable but a check disagreed)
  100 clean valid sheet
(see app/confidence.py — this script mirrors those exact scores in set-based SQL so it
runs over all ~350k rows in seconds rather than row-by-row.)

Run LOCALLY against $DATABASE_URL, like the app. Dry-run prints the distribution and
writes nothing; --commit applies it. Idempotent — re-running recomputes from current
sheet state.

    python -m scripts.backfill_confidence            # dry run
    python -m scripts.backfill_confidence --commit   # apply
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app import confidence as C  # noqa: E402

# One set-based UPDATE. For each pu_results row we look up its matching pu_sheet
# (same pu_code + election_type + year) and whether it has a correction evidence row,
# then assign the lowest applicable score. Mirrors app/confidence.score_from_sheet.
_UPDATE_SQL = f"""
WITH scored AS (
    SELECT r.id,
           CASE
               WHEN c.pu_code IS NOT NULL THEN {C.SCORE_INFLATED}
               WHEN LOWER(COALESCE(s.legibility,'')) IN ('illegible','blurry')
                    OR LOWER(COALESCE(s.status,'')) = 'blurry' THEN {C.SCORE_BLURRY}
               WHEN s.pu_code IS NULL
                    OR COALESCE(s.sheet_url,'') = ''
                    OR LOWER(COALESCE(s.sheet_status,'')) IN ('no_sheet','dead','') THEN {C.SCORE_MISSING_SHEET}
               WHEN LOWER(COALESCE(s.status,'')) = 'unsure' THEN {C.SCORE_UNSURE}
               ELSE {C.SCORE_VALID}
           END AS score
    FROM pu_results r
    LEFT JOIN pu_sheets s
           ON s.pu_code = r.pu_code
          AND s.election_type = r.election_type
          AND s.year = r.year
    LEFT JOIN (
        SELECT DISTINCT pu_code, election_type, year
        FROM evidence WHERE kind = 'correction'
    ) c ON c.pu_code = r.pu_code
       AND c.election_type = r.election_type
       AND c.year = r.year
)
UPDATE pu_results r
   SET confidence = scored.score,
       confidence_band = CASE
           WHEN scored.score >= 80 THEN 'high'
           WHEN scored.score >= 50 THEN 'medium'
           ELSE 'low' END
  FROM scored
 WHERE scored.id = r.id
"""

_DISTRIB_SQL = """
SELECT COALESCE(confidence, -1) AS score, confidence_band, count(*)
FROM pu_results GROUP BY 1, 2 ORDER BY 1
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="apply the update (default: dry run)")
    args = ap.parse_args()

    db = SessionLocal() if SessionLocal else None
    if db is None:
        sys.exit("DATABASE_URL not set — aborting.")
    try:
        total = db.execute(text("SELECT count(*) FROM pu_results")).scalar()
        print(f"pu_results rows: {total:,}")
        print(f"score rules: inflated={C.SCORE_INFLATED} blurry={C.SCORE_BLURRY} "
              f"missing_sheet={C.SCORE_MISSING_SHEET} unsure={C.SCORE_UNSURE} valid={C.SCORE_VALID}")

        if not args.commit:
            print("\nDRY RUN — computing the distribution WITHOUT writing:")
            preview = f"WITH u AS ({_UPDATE_SQL.replace('UPDATE pu_results r', 'SELECT r.id,')})"  # not used
            # simpler: run the scoring CTE as a SELECT to preview
            sel = _UPDATE_SQL[_UPDATE_SQL.index("WITH"):_UPDATE_SQL.index("UPDATE")]
            sel += "SELECT score, count(*) FROM scored GROUP BY score ORDER BY score"
            for score, n in db.execute(text(sel)).all():
                band = C.band(score)
                print(f"  score {score:>3}  ({band:<6})  {n:,}")
            print("\nNo writes. Re-run with --commit to apply.")
            return

        print("\nApplying confidence scores...")
        res = db.execute(text(_UPDATE_SQL))
        db.commit()
        print(f"Updated {res.rowcount:,} pu_results rows.")
        print("\nResulting distribution:")
        for score, band, n in db.execute(text(_DISTRIB_SQL)).all():
            label = "unscored" if score == -1 else f"score {int(score)}"
            print(f"  {label:<12} {band or '-':<8} {n:,}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
