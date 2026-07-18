"""The model that turns a scenario's assumptions into a per-state projection.

Everything here is pure arithmetic on vote counts so a projection is fully
explainable: every state prediction carries a `detail` trace of each politician
swing and trend shift that produced it, which the frontend renders when you
click a prediction.

Baseline = the verified 2023 presidential result for the state. A politician who
ran re-allocates a bloc of votes to his NEW party; a trend nudges a share of the
electorate toward a party. Totals are conserved (votes are moved, not created).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PartyHistory, Politician, StateResultV, StateResultParty

# The party buckets the baseline is expressed in. Anything else folds into "others".
PARTIES = ["APC", "PDP", "LP", "NNPP", "others"]


def _bucket(party: str) -> str:
    p = (party or "").strip().upper()
    return p if p in ("APC", "PDP", "LP", "NNPP") else "others"


def resolve_old_party(db: Session, politician_id: int) -> str:
    """The party bucket a politician's votes currently sit in — his most recent
    recorded run's party, falling back to his profile party, then 'others'."""
    last = db.scalars(
        select(PartyHistory)
        .where(PartyHistory.politician_id == politician_id, PartyHistory.party != "")
        .order_by(PartyHistory.year.desc())
    ).first()
    if last and last.party:
        return _bucket(last.party)
    pol = db.get(Politician, politician_id)
    return _bucket(pol.party if pol else "")


def baseline_votes(db: Session, state: str) -> dict[str, int] | None:
    """The 2023 per-party vote counts for a state, or None if we have no result. Reads the
    unified state-level presidential result (StateResultV + StateResultParty)."""
    row = db.scalar(select(StateResultV).where(
        StateResultV.state == state, StateResultV.year == "2023",
        StateResultV.election_type == "presidential"))
    if row is None:
        return None
    parties = {pp.party: (pp.votes or 0) for pp in db.scalars(
        select(StateResultParty).where(StateResultParty.state_result_id == row.id)).all()}
    return {
        "APC": parties.get("APC", 0), "PDP": parties.get("PDP", 0),
        "LP": parties.get("LP", 0), "NNPP": parties.get("NNPP", 0),
        "others": sum(v for p, v in parties.items() if p not in ("APC", "PDP", "LP", "NNPP")),
    }


def _applies(scope: str, home_state: str, state: str) -> bool:
    if scope == "local":
        return home_state == state
    # national / election apply everywhere (a presidential race is nationwide)
    return True


def _withdraw(votes: dict[str, int], amount: float, protect: str, prefer: str | None) -> dict[str, float]:
    """Remove `amount` votes from the pool, drawing first from `prefer` (the
    politician's old party), then proportionally from every party except
    `protect` (the destination). Returns {party: votes_removed}."""
    removed: dict[str, float] = {}
    remaining = amount
    if prefer and prefer != protect and votes.get(prefer, 0) > 0 and remaining > 0:
        take = min(votes[prefer], remaining)
        removed[prefer] = take
        remaining -= take
    if remaining > 0:
        donors = {p: v - removed.get(p, 0) for p, v in votes.items() if p != protect}
        pool = sum(v for v in donors.values() if v > 0)
        if pool > 0:
            for p, avail in donors.items():
                if avail <= 0:
                    continue
                share = min(avail, remaining * (avail / pool))
                removed[p] = removed.get(p, 0) + share
    return removed


def compute_state(
    db: Session,
    state: str,
    politicians: list[dict],
    trends: list[dict],
) -> dict | None:
    """Project one state. `politicians` items: {id, name, new_party, delta_popularity,
    influence_pct, scope, home_state, old_party}. `trends` items: {name, shift_pct,
    target_party, scope_states}. Returns a detail dict, or None if no baseline."""
    base = baseline_votes(db, state)
    if base is None:
        return None
    votes: dict[str, float] = {p: float(base.get(p, 0)) for p in PARTIES}
    baseline_total = sum(votes.values())
    steps: list[dict] = []

    # --- politician swings ---
    for pol in politicians:
        if not _applies(pol["scope"], pol.get("home_state", ""), state):
            continue
        new_party = _bucket(pol["new_party"])
        infl = max(0.0, float(pol.get("influence_pct") or 0))
        delta = float(pol.get("delta_popularity") or 0)
        swing = baseline_total * (infl / 100.0) * (1 + delta / 100.0)
        if swing <= 0:
            continue
        # cap: can't move more than what everyone else holds
        movable = sum(v for p, v in votes.items() if p != new_party)
        swing = min(swing, movable)
        if swing <= 0:
            continue
        removed = _withdraw(votes, swing, protect=new_party, prefer=pol.get("old_party"))
        for p, amt in removed.items():
            votes[p] = max(0.0, votes[p] - amt)
        votes[new_party] = votes.get(new_party, 0) + swing
        steps.append({
            "kind": "politician",
            "id": pol.get("id"),
            "name": pol.get("name", ""),
            "from_party": pol.get("old_party", "others"),
            "to_party": new_party,
            "to_party_label": (pol.get("new_party") or new_party).upper(),
            "votes": round(swing),
            "delta_popularity": delta,
            "influence_pct": infl,
            "scope": pol["scope"],
        })

    # --- trend shifts ---
    for tr in trends:
        states = tr.get("scope_states") or []
        if states and state not in states:
            continue
        target = _bucket(tr["target_party"])
        shift_pct = float(tr.get("shift_pct") or 0)
        if shift_pct <= 0:
            continue
        total = sum(votes.values())
        amount = total * (shift_pct / 100.0)
        movable = sum(v for p, v in votes.items() if p != target)
        amount = min(amount, movable)
        if amount <= 0:
            continue
        removed = _withdraw(votes, amount, protect=target, prefer=None)
        for p, amt in removed.items():
            votes[p] = max(0.0, votes[p] - amt)
        votes[target] = votes.get(target, 0) + amount
        steps.append({
            "kind": "trend",
            "name": tr.get("name", ""),
            "to_party": target,
            "shift_pct": shift_pct,
            "votes": round(amount),
        })

    result_votes = {p: round(votes.get(p, 0)) for p in PARTIES}
    total = sum(result_votes.values()) or 1
    result_pct = {p: round(100 * result_votes[p] / total, 1) for p in PARTIES}
    non_zero = {p: v for p, v in result_pct.items() if v > 0}
    leader = max(non_zero, key=lambda p: non_zero[p]) if non_zero else ""

    return {
        "state": state,
        "baseline_votes": {p: round(base.get(p, 0)) for p in PARTIES},
        "baseline_total": round(baseline_total),
        "steps": steps,
        "result_votes": result_votes,
        "result_pct": result_pct,
        "total_votes": total,
        "leader": leader,
    }
