"""Seed the predictions table with illustrative, already-aggregated data.

Real data would be crunched from raw contributor traces upstream; this just
gives the map something to render across weeks and election types.
"""
import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Prediction

PARTY_ORDER = ["APC", "PDP", "LP", "NNPP", "APGA", "SDP"]

WEEKS = ["2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29", "2026-07-06"]

# Base leanings (latest week): state -> {governor: (party, pct), presidential: (party, pct)}
BASE = {
    "Sokoto": (("APC", 47), ("APC", 52)), "Zamfara": (("PDP", 42), ("APC", 45)), "Katsina": (("APC", 50), ("APC", 55)),
    "Kano": (("NNPP", 43), ("NNPP", 49)), "Jigawa": (("APC", 47), ("APC", 50)), "Yobe": (("APC", 56), ("APC", 61)),
    "Borno": (("APC", 58), ("APC", 60)), "Kebbi": (("APC", 53), ("APC", 56)), "Niger": (("APC", 46), ("APC", 48)),
    "Kaduna": (("APC", 41), ("APC", 44)), "Bauchi": (("PDP", 44), ("APC", 43)), "Gombe": (("APC", 49), ("APC", 52)),
    "Adamawa": (("PDP", 41), ("PDP", 45)), "Kwara": (("APC", 48), ("APC", 50)), "FCT": (("LP", 40), ("LP", 59)),
    "Plateau": (("PDP", 43), ("LP", 47)), "Nasarawa": (("APC", 42), ("LP", 41)), "Taraba": (("PDP", 44), ("PDP", 46)),
    "Kogi": (("APC", 45), ("APC", 47)), "Benue": (("APC", 39), ("LP", 44)), "Oyo": (("PDP", 46), ("APC", 44)),
    "Osun": (("PDP", 46), ("APC", 43)), "Ekiti": (("APC", 51), ("APC", 54)), "Ondo": (("APC", 49), ("APC", 52)),
    "Ogun": (("APC", 47), ("APC", 46)), "Lagos": (("APC", 44), ("LP", 47)), "Edo": (("PDP", 42), ("LP", 45)),
    "Enugu": (("LP", 44), ("LP", 63)), "Ebonyi": (("APC", 46), ("LP", 52)), "Anambra": (("APGA", 47), ("LP", 60)),
    "Imo": (("APC", 41), ("LP", 55)), "Abia": (("LP", 45), ("LP", 66)), "Delta": (("PDP", 48), ("PDP", 50)),
    "Bayelsa": (("PDP", 55), ("PDP", 58)), "Rivers": (("PDP", 49), ("PDP", 47)), "Akwa Ibom": (("PDP", 52), ("PDP", 54)),
    "Cross River": (("APC", 43), ("APC", 44)),
}


def _rand(*parts) -> float:
    """Deterministic pseudo-random in [0, 1) from the given key parts."""
    h = hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _base_scores(leader: str, pct: int) -> dict[str, float]:
    others = [p for p in PARTY_ORDER if p != leader][:3]
    rem = 100 - pct
    scores = {leader: float(pct)}
    for p, frac in zip(others, (0.5, 0.3, 0.2)):
        scores[p] = round(rem * frac, 1)
    return scores


def _rows():
    n = len(WEEKS)
    for state, (gov, pres) in BASE.items():
        types = {
            "governor": gov,
            "presidential": pres,
            "senate": (gov[0], max(36, gov[1] - 2)),  # senate tracks the governorship, slightly softer
        }
        for etype, (leader, pct) in types.items():
            base = _base_scores(leader, pct)
            for wi, week in enumerate(WEEKS):
                # latest week == base leanings; earlier weeks drift more, so the
                # leader flips in genuinely close states as you step back in time.
                factor = (n - 1 - wi) / (n - 1)
                raw = {p: max(1.0, s + (_rand(state, etype, p, wi) - 0.5) * 16 * factor) for p, s in base.items()}
                total = sum(raw.values())
                for party, v in raw.items():
                    yield Prediction(
                        state=state,
                        election_type=etype,
                        party=party,
                        score=round(v / total * 100, 1),
                        measurement_week=week,
                    )


def seed_predictions(db: Session) -> int:
    """Insert seed rows if the predictions table is empty. Returns rows added."""
    existing = db.scalar(select(func.count()).select_from(Prediction))
    if existing:
        return 0
    rows = list(_rows())
    db.add_all(rows)
    db.commit()
    return len(rows)
