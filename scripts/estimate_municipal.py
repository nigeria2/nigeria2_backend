"""Clear and rebuild the 2027 per-ward predictions for the municipal LGA (AMAC — where
Peter Obi did best in 2023) with a reasoned, component-based estimate.

Each 2027 ticket gets one prediction per ward, decomposed into:
  - Candidate Popularity   : the presidential candidate's own 2023 vote in the ward,
                             retained with some decay.
  - Running-mate Popularity: the votes the VP personally delivered in 2023 (his own 2023
                             party result in the ward), transferred to the joint ticket.
                             The VP is linked as a politician on this component, so we can
                             match him against what he actually delivered last time.
                             Kwankwaso (NNPP, 2023) delivered real votes; Shettima did not
                             run in his own right in 2023, so his contribution is 0.
  - Party Popularity       : structural party support, a small share of the ward turnout.

Run from backend/ with DATABASE_URL set:
    export $(grep -v '^#' .env | grep DATABASE_URL)
    .venv/Scripts/python.exe -m scripts.estimate_municipal
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import WardPrediction, PredictionComponent, Lga  # noqa: E402
from app.seed import estimate_municipal_predictions  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        n = estimate_municipal_predictions(db, clear=True)
        print(f"Rebuilt {n} ward prediction(s).")

        # Show what we produced, per candidate, so the estimate can be eyeballed.
        rows = db.scalars(select(WardPrediction).order_by(WardPrediction.ward_code)).all()
        if not rows:
            print("No predictions found.")
            return
        lga = db.get(Lga, rows[0].lga_id)
        print(f"\nLGA: {lga.name if lga else rows[0].lga_id} (lga_id={rows[0].lga_id})\n")
        by_cand: dict = {}
        for r in rows:
            by_cand.setdefault(r.politician_id, {"party": r.party, "votes": 0})
            by_cand[r.politician_id]["votes"] += r.votes
        for pid, agg in sorted(by_cand.items(), key=lambda kv: kv[1]["votes"], reverse=True):
            from app.models import Politician
            p = db.get(Politician, pid)
            print(f"  {p.name if p else pid} ({agg['party']}): {agg['votes']:,} across all wards")

        # One ward, fully broken out, as a sanity check of the components.
        sample = rows[0]
        comps = db.scalars(
            select(PredictionComponent)
            .where(PredictionComponent.ward_prediction_id == sample.id)
            .order_by(PredictionComponent.seq)
        ).all()
        print(f"\nExample ward '{sample.ward_code}' — {by_cand and ''}prediction {sample.votes:,}:")
        for c in comps:
            tag = f" [politician_id={c.politician_id}]" if c.politician_id else ""
            print(f"    {c.reason}: {c.votes:,}{tag}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
