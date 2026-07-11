"""Clear and rebuild our reasoned 2027 per-ward predictions for the LGAs we have modelled
(AMAC and Ikot Ekpene) using component-based estimates.

Each 2027 ticket gets one prediction per ward, decomposed into:
  - Candidate Popularity   : the presidential candidate's own 2023 vote, retained.
  - Running-mate Popularity: the votes the VP personally delivered in 2023, transferred.
  - Supporter Popularity   : a backer not on the ticket (e.g. a governor) delivering a
                             share of the base he commands. In Ikot Ekpene, PDP governor
                             Umo Eno backs Tinubu/Shettima.
  - Party Popularity       : structural party support, a share of the ward turnout.
The VP and supporters are linked as politicians, matched against what they delivered.

Run from backend/ with DATABASE_URL set:
    export $(grep -v '^#' .env | grep DATABASE_URL)
    .venv/Scripts/python.exe -m scripts.estimate_municipal
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from collections import defaultdict  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import WardPrediction, PredictionComponent, Lga, Politician  # noqa: E402
from app.seed import estimate_all_lga_predictions  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        n = estimate_all_lga_predictions(db, clear=True)
        print(f"Rebuilt {n} ward prediction(s).\n")

        rows = db.scalars(select(WardPrediction).order_by(WardPrediction.lga_id, WardPrediction.ward_code)).all()
        by_lga: dict[int, list] = defaultdict(list)
        for r in rows:
            by_lga[r.lga_id].append(r)

        for lga_id, lrows in by_lga.items():
            lga = db.get(Lga, lga_id)
            print(f"== {lga.name if lga else lga_id} (lga_id={lga_id}) ==")
            agg: dict = {}
            for r in lrows:
                agg.setdefault(r.politician_id, {"party": r.party, "votes": 0})
                agg[r.politician_id]["votes"] += r.votes
            for pid, a in sorted(agg.items(), key=lambda kv: kv[1]["votes"], reverse=True):
                p = db.get(Politician, pid)
                print(f"   {p.name if p else pid} ({a['party']}): {a['votes']:,}")

            # one ward broken into components, per ticket, as a sanity check
            sample_code = lrows[0].ward_code
            for r in [x for x in lrows if x.ward_code == sample_code]:
                p = db.get(Politician, r.politician_id)
                print(f"   ward '{sample_code}' — {p.name if p else r.politician_id}: {r.votes:,}")
                comps = db.scalars(select(PredictionComponent)
                                   .where(PredictionComponent.ward_prediction_id == r.id)
                                   .order_by(PredictionComponent.seq)).all()
                for c in comps:
                    sp = db.get(Politician, c.politician_id) if c.politician_id else None
                    tag = f" -> {sp.name}" if sp else ""
                    print(f"       {c.reason}: {c.votes:,}{tag}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
