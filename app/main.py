"""Minimal FastAPI backend for Nigeria 2.0."""
import json
import os
import pathlib
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .auth import create_token, current_user, require_admin, verify_google_credential
from .db import SessionLocal, engine, get_db
from .models import (
    Analysis,
    DeclaredCandidate,
    Governor,
    GovernorHistory,
    HouseMember,
    InterestedUser,
    Lga,
    LgaResult,
    Party,
    PartyElection,
    PartyHistory,
    PollingUnit,
    ElectionResult,
    Politician,
    PoliticianAssessment,
    PoliticianPhoto,
    Prediction,
    PredictionScenario,
    ProblemUnit,
    ScenarioPolitician,
    ScenarioTrend,
    Senator,
    State,
    StatePrediction,
    StatePresidential,
    User,
    Ward,
    WardResult,
)
from . import prediction_worker
from .history_ingest import PARTY_NAMES, seed_election_history
from .schemas import (
    AnalysisIn,
    AssessmentIn,
    DeclaredCandidateIn,
    GoogleAuthIn,
    JoinIn,
    JoinOut,
    PartyElectionSetIn,
    PhotoSubmitIn,
    PoliticianIn,
    PredictionSetIn,
    ProfileUpdate,
    ScenarioIn,
    ScenarioPoliticianIn,
    ScenarioTrendIn,
    StatePredictionIn,
    StatePredictionUpdate,
)
from .seed import (
    BASE,
    dedupe_politicians,
    migrate_assessment_lgas,
    seed_analyses,
    seed_governor_2023_results,
    seed_governors_current,
    seed_governors_history,
    seed_house_members,
    seed_presidential_2019,
    seed_presidential_2023,
    seed_presidential_primaries,
    seed_presidential_states,
    seed_senate_2023,
    seed_lga_results,
    seed_lgas,
    refresh_lga_names,
    seed_parties,
    seed_party_elections,
    seed_party_history,
    seed_politicians,
    seed_predictions,
    seed_problem_units,
    seed_polling_units,
    seed_senators,
    seed_state_predictions,
    seed_states,
    seed_ward_results,
    seed_wards,
)

STATE_NAMES = sorted(BASE.keys())
_ELECTIONS_DIR = pathlib.Path(__file__).resolve().parent / "data" / "elections"


def run_migrations() -> None:
    """Apply Alembic migrations up to head. Called once on startup."""
    if engine is None:
        print("[startup] DATABASE_URL not set — skipping migrations")
        return
    from alembic import command
    from alembic.config import Config

    ini = pathlib.Path(__file__).resolve().parent.parent / "alembic.ini"
    command.upgrade(Config(str(ini)), "head")
    print("[startup] migrations applied")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        run_migrations()
    except Exception as exc:  # don't prevent boot; surface in logs
        print(f"[startup] migration error: {exc}")
    try:
        if SessionLocal is not None:
            with SessionLocal() as db:
                added = seed_predictions(db)
                if added:
                    print(f"[startup] seeded {added} prediction rows")
                analyses = seed_analyses(db)
                if analyses:
                    print(f"[startup] seeded {analyses} analysis rows")
                parties = seed_parties(db)
                if parties:
                    print(f"[startup] seeded {parties} parties")
                rel = seed_party_elections(db)
                if rel:
                    print(f"[startup] seeded {rel} party-election links")
                pu = seed_problem_units(db)
                if pu:
                    print(f"[startup] seeded {pu} problem units")
                # The seeded "past performance" (2023 result) predictions were removed.
                removed_pp = db.execute(
                    delete(StatePrediction).where(StatePrediction.source == "past_performance")
                ).rowcount
                if removed_pp:
                    db.commit()
                    print(f"[startup] removed {removed_pp} past-performance predictions")
                pol = seed_politicians(db)
                if pol:
                    print(f"[startup] seeded {pol} politicians")
                lga = seed_lga_results(db)
                if lga:
                    print(f"[startup] seeded {lga} LGA results")
                lgc = seed_lgas(db)
                if lgc:
                    print(f"[startup] seeded {lgc} canonical LGAs")
                lgr = refresh_lga_names(db)
                if lgr:
                    print(f"[startup] corrected {lgr} stale LGA names")
                sts = seed_states(db)
                if sts:
                    print(f"[startup] seeded {sts} states")
                ph = seed_party_history(db)
                if ph:
                    print(f"[startup] seeded {ph} party-history rows")
                sen = seed_senators(db)
                if sen:
                    print(f"[startup] seeded {sen} senators")
                g23 = seed_governor_2023_results(db)
                if g23:
                    print(f"[startup] seeded {g23} 2023 governor candidate results")
                s23 = seed_senate_2023(db)
                if s23:
                    print(f"[startup] seeded {s23} 2023 senate candidate results")
                p23 = seed_presidential_2023(db)
                if p23:
                    print(f"[startup] seeded {p23} 2023 presidential candidates")
                pst = seed_presidential_states(db)
                if pst:
                    print(f"[startup] seeded {pst} state presidential results")
                ppr = seed_presidential_primaries(db)
                if ppr:
                    print(f"[startup] seeded {ppr} presidential primary results")
                p19 = seed_presidential_2019(db)
                if p19:
                    print(f"[startup] seeded {p19} 2019 presidential candidates")
                hist = seed_election_history(db, _ELECTIONS_DIR.parent / "history")
                if hist:
                    print(f"[startup] seeded {hist} historical election results")
                gov = seed_governors_current(db)
                if gov:
                    print(f"[startup] seeded {gov} current governors")
                gh = seed_governors_history(db)
                if gh:
                    print(f"[startup] seeded {gh} governor-history rows")
                dd = dedupe_politicians(db)
                if dd:
                    print(f"[startup] merged {dd} duplicate politician records")
                ma = migrate_assessment_lgas(db)
                if ma:
                    print(f"[startup] migrated {ma} assessments to LGA ids")
                hm = seed_house_members(db)
                if hm:
                    print(f"[startup] seeded {hm} house members")
                wd = seed_wards(db)
                if wd:
                    print(f"[startup] seeded {wd} wards")
                pu = seed_polling_units(db)
                if pu:
                    print(f"[startup] seeded {pu} polling units")
                wr = seed_ward_results(db)
                if wr:
                    print(f"[startup] seeded {wr} ward results")
    except Exception as exc:
        print(f"[startup] seed error: {exc}")
    # Relaunch any model job that was mid-run when the process last died.
    try:
        resumed = prediction_worker.resume_running()
        if resumed:
            print(f"[startup] resumed {resumed} running prediction scenario(s)")
    except Exception as exc:
        print(f"[startup] scenario resume error: {exc}")
    yield


app = FastAPI(title="Nigeria 2.0 API", version="0.36.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nigeria2.com",
        "https://www.nigeria2.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def user_to_dict(u: User) -> dict:
    try:
        known = json.loads(u.known_states) if u.known_states else []
    except Exception:
        known = []
    return {
        "id": u.id,
        "email": u.email,
        "email_verified": u.email_verified,
        "full_name": u.full_name,
        "given_name": u.given_name,
        "family_name": u.family_name,
        "picture": u.picture,
        "is_admin": u.is_admin,
        "phone": u.phone,
        "gender": u.gender,
        "year_of_birth": u.year_of_birth,
        "home_state": u.home_state,
        "home_lga": u.home_lga,
        "residence_state": u.residence_state,
        "voter_status": u.voter_status,
        "known_states": known,
        "bio": u.bio,
        "onboarded": u.onboarded,
    }


@app.get("/")
def root():
    return {"service": "nigeria2-backend", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/ping")
def ping():
    return {"ping": "pong"}


@app.get("/db/health")
def db_health():
    if engine is None:
        return JSONResponse(status_code=503, content={"db": "unconfigured"})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"db": "error", "detail": str(exc)})


# --- public: join the movement (creates an interested user pending Google sign-in) ---
@app.post("/api/join", response_model=JoinOut, status_code=201)
def join(payload: JoinIn, db: Session = Depends(get_db)):
    # If they already have a full account, don't add a pending record.
    if db.scalar(select(User).where(func.lower(User.email) == payload.email.lower())):
        return JoinOut(id=0)
    existing = db.scalar(select(InterestedUser).where(func.lower(InterestedUser.email) == payload.email.lower()))
    rec = existing or InterestedUser(email=payload.email)
    rec.full_name = payload.full_name
    rec.location = payload.location
    rec.state = payload.state
    rec.mobile = payload.mobile
    if existing is None:
        db.add(rec)
    db.commit()
    db.refresh(rec)
    return JoinOut(id=rec.id)


# --- predictions (public; already aggregated from traces) ---
@app.get("/api/predictions/meta")
def predictions_meta(db: Session = Depends(get_db)):
    weeks = [
        w for (w,) in db.execute(
            select(Prediction.measurement_week).distinct().order_by(Prediction.measurement_week.desc())
        ).all()
    ]
    types = [t for (t,) in db.execute(select(Prediction.election_type).distinct()).all()]
    order = {"presidential": 0, "governor": 1, "senate": 2}
    types.sort(key=lambda t: order.get(t, 9))
    return {"weeks": weeks, "election_types": types}


@app.get("/api/predictions")
def predictions(election_type: str, week: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Prediction).where(
            Prediction.election_type == election_type,
            Prediction.measurement_week == week,
        )
    ).all()
    return [{"state": r.state, "party": r.party, "score": r.score} for r in rows]


@app.get("/api/predictions/trend")
def predictions_trend(db: Session = Depends(get_db)):
    """National party share per measurement week, for each election type."""
    party_sum: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    state_set: dict[tuple[str, str], set[str]] = defaultdict(set)
    for p in db.scalars(select(Prediction)).all():
        party_sum[(p.election_type, p.measurement_week)][p.party] += p.score
        state_set[(p.election_type, p.measurement_week)].add(p.state)
    out: dict[str, list[dict]] = defaultdict(list)
    for et, week in sorted(party_sum.keys()):
        n = len(state_set[(et, week)]) or 1
        shares = {party: round(s / n, 1) for party, s in party_sum[(et, week)].items()}
        out[et].append({"week": week, "shares": shares})
    return out


# --- political parties (public) ---
@app.get("/api/parties")
def list_parties(db: Session = Depends(get_db)):
    rows = db.scalars(select(Party).order_by(Party.name)).all()
    # "Active" = fielded at least one candidate in the 2019 general elections
    # (governor/presidential/senate/house) -- our most complete single-year
    # dataset, so the most reliable signal for "still contests elections".
    active_2019 = {
        (a or "").strip().upper()
        for a in db.scalars(select(PartyHistory.party).where(PartyHistory.year == "2019").distinct()).all()
    }
    return [
        {
            "acronym": p.acronym,
            "name": p.name,
            "chairman": p.chairman,
            "secretary": p.secretary,
            "treasurer": p.treasurer,
            "financial_secretary": p.financial_secretary,
            "legal_adviser": p.legal_adviser,
            "address": p.address,
            "active": p.acronym.strip().upper() in active_2019,
        }
        for p in rows
    ]


@app.get("/api/parties/elections")
def parties_by_election(db: Session = Depends(get_db)):
    """Which party acronyms are relevant for each election type."""
    out: dict[str, list[str]] = {}
    for r in db.scalars(select(PartyElection)).all():
        out.setdefault(r.election_type, []).append(r.party_acronym)
    return out


# --- 2023 problem polling units (public) ---
def problem_unit_to_dict(u: ProblemUnit) -> dict:
    return {
        "id": u.id,
        "state": u.state,
        "lga": u.lga,
        "ward": u.ward,
        "polling_unit": u.polling_unit,
        "pu_code": u.pu_code,
        "anomaly_type": u.anomaly_type,
        "severity": u.severity,
        "description": u.description,
        "registered_voters": u.registered_voters,
        "accredited_voters": u.accredited_voters,
        "votes_cast": u.votes_cast,
        "election_year": u.election_year,
    }


@app.get("/api/problem-units")
def list_problem_units(
    state: str | None = None,
    anomaly_type: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(ProblemUnit)
    if state:
        stmt = stmt.where(ProblemUnit.state == state)
    if anomaly_type:
        stmt = stmt.where(ProblemUnit.anomaly_type == anomaly_type)
    stmt = stmt.order_by(ProblemUnit.state, ProblemUnit.lga)
    return [problem_unit_to_dict(u) for u in db.scalars(stmt).all()]


@app.get("/api/problem-units/meta")
def problem_units_meta(db: Session = Depends(get_db)):
    states = [s for (s,) in db.execute(select(ProblemUnit.state).distinct().order_by(ProblemUnit.state)).all()]
    types = [t for (t,) in db.execute(select(ProblemUnit.anomaly_type).distinct().order_by(ProblemUnit.anomaly_type)).all()]
    total = db.scalar(select(func.count()).select_from(ProblemUnit))
    return {"states": states, "anomaly_types": types, "total": total}


# --- public per-state detail (predictions board + political heavyweights) ---
def _public_prediction_dict(p: StatePrediction) -> dict:
    try:
        scores = json.loads(p.scores) if p.scores else {}
    except Exception:
        scores = {}
    return {
        "id": p.id,
        "state": p.state,
        "election_type": p.election_type,
        "source": p.source,
        "label": p.label,
        "author_name": p.author_name,
        "leading_party": p.leading_party,
        "scores": scores,
        "notes": p.notes,
        "year": p.year,
        "scenario_id": p.scenario_id,
        "has_detail": bool(p.source == "model" and p.detail and p.detail != "{}"),
    }


def _lga_result_dict(x: LgaResult) -> dict:
    try:
        scores = json.loads(x.scores) if x.scores else {}
    except Exception:
        scores = {}
    return {"lga": x.lga, "leading_party": x.leading_party, "scores": scores, "total_votes": x.total_votes, "year": x.year}


def _load_list(s: str) -> list:
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def _lga_norm(s) -> str:
    return "".join(c for c in str(s).lower() if c.isalnum())


_LGA_NAME_CACHE: dict[int, str] | None = None


def _lga_names(db: Session) -> dict[int, str]:
    """id -> current canonical LGA name (cached; refreshed on process restart)."""
    global _LGA_NAME_CACHE
    if _LGA_NAME_CACHE is None:
        _LGA_NAME_CACHE = {l.id: l.name for l in db.scalars(select(Lga)).all()}
    return _LGA_NAME_CACHE


def _lga_label(v, names: dict[int, str] | None) -> str | None:
    """Resolve a stored LGA reference (id) to its current name."""
    if isinstance(v, int):
        return (names or {}).get(v)
    return str(v) or None  # legacy fallback (should not occur after migration)


def _assess_agg(assessments: list, lga_names: dict[int, str] | None = None) -> dict:
    vals = [a.electoral_value for a in assessments]
    counter: Counter = Counter()
    for a in assessments:
        for ref in _load_list(a.influential_lgas):
            name = _lga_label(ref, lga_names)
            if name:
                counter[name] += 1
    return {
        "avg_electoral_value": round(sum(vals) / len(vals)) if vals else None,
        "assessments": len(vals),
        "top_lgas": [{"lga": k, "count": v} for k, v in counter.most_common(6)],
    }


def politician_to_dict(p: Politician, assessments: list, runs: list | None = None, lga_names: dict[int, str] | None = None) -> dict:
    d = {"id": p.id, "name": p.name, "state": p.state, "title": p.title, "party": p.party, "note": p.note, "photo": p.photo or "",
         "aka": _load_list(p.aka)}
    d.update(_assess_agg(assessments, lga_names))
    runs = runs or []
    voted = [r for r in runs if r.votes and r.election_type != "primary"]  # primaries = delegate votes, not vote-pull
    best = max(voted, key=lambda r: r.votes) if voted else None
    d["max_votes"] = best.votes if best else None
    d["best_run"] = (
        {"year": best.year, "election_type": best.election_type, "votes": best.votes, "percent": best.percent, "party": best.party}
        if best else None
    )
    d["runs_count"] = len(voted)
    return d


# Party -> the StatePresidential column holding that ticket's by-state votes.
_PRES_PARTY_COL = {"APC": "apc", "PDP": "pdp", "LP": "lp", "NNPP": "nnpp"}


def _presidential_state_votes(db: Session, runs: list) -> list[dict]:
    """A presidential candidate's by-state vote breakdown, states sorted by votes
    (where they polled the most first). Pulled from the official StatePresidential
    table, which only carries the four major-party tickets — everyone else (minor
    candidates, non-presidential runs) yields no by-state rows and returns []."""
    out: list[dict] = []
    seen_years: set[int] = set()
    for r in runs:
        if r.election_type != "presidential":
            continue
        col = _PRES_PARTY_COL.get(r.party)
        if col is None:
            continue
        try:
            yr = int(r.year)
        except (TypeError, ValueError):
            continue
        if yr in seen_years:
            continue
        rows = db.scalars(select(StatePresidential).where(StatePresidential.year == yr)).all()
        if not rows:
            continue
        seen_years.add(yr)
        states = sorted(
            (
                {"state": s.state, "votes": getattr(s, col) or 0, "total": s.total_votes or 0,
                 "won": s.winner == r.party}
                for s in rows
            ),
            key=lambda x: x["votes"], reverse=True,
        )
        out.append({"year": str(yr), "party": r.party, "states": states})
    return out


def _is_heavyweight(d: dict) -> bool:
    """Hide fringe candidates (a handful of real, known votes in the low
    single digits -- from a large ward or a joke campaign, not a real
    contender) from the heavyweight boards. Anyone whose best vote count is
    unknown (no non-primary run on record) is kept, since "unknown" isn't
    evidence of being a fringe candidate. Their full record is still visible
    from a state's full politician list -- this only trims the headline board."""
    return d["max_votes"] is None or d["max_votes"] >= 10


def _runs_map(db: Session, pol_ids: list[int]) -> dict[int, list]:
    """Map politician_id -> their PartyHistory rows (election runs), oldest first."""
    out: dict[int, list] = defaultdict(list)
    if not pol_ids:
        return out
    for h in db.scalars(
        select(PartyHistory).where(PartyHistory.politician_id.in_(pol_ids)).order_by(PartyHistory.year)
    ).all():
        out[h.politician_id].append(h)
    return out


@app.get("/api/states/{state}")
def state_detail(state: str, db: Session = Depends(get_db)):
    preds = db.scalars(
        select(StatePrediction).where(StatePrediction.state == state).order_by(StatePrediction.source, StatePrediction.created_at.desc())
    ).all()
    pols = db.scalars(select(Politician).where(Politician.state == state).order_by(Politician.id)).all()
    lgas = db.scalars(select(LgaResult).where(LgaResult.state == state).order_by(LgaResult.lga)).all()
    pol_assess: dict[int, list] = defaultdict(list)
    if pols:
        for a in db.scalars(select(PoliticianAssessment).where(PoliticianAssessment.politician_id.in_([p.id for p in pols]))).all():
            pol_assess[a.politician_id].append(a)
    pol_runs = _runs_map(db, [p.id for p in pols])
    lga_names = _lga_names(db)
    st = db.scalar(select(State).where(State.name == state))
    facts = None
    if st is not None:
        facts = {
            "code": st.code, "capital": st.capital, "area_sq_km": st.area_sq_km,
            "census_1991": st.census_1991, "census_2006": st.census_2006, "population_projection": st.population_projection,
            "active_phone_2021": st.active_phone_2021, "active_phone_2020": st.active_phone_2020,
            "newly_registered_voters_2022": st.newly_registered_voters_2022,
            "voters_presidential_2019": st.voters_presidential_2019,
            "buhari_votes_2019": st.buhari_votes_2019, "atiku_votes_2019": st.atiku_votes_2019,
            "total_votes_2019": st.total_votes_2019, "votes_2023": st.votes_2023,
            "nin_total": st.nin_total, "nin_male": st.nin_male, "nin_female": st.nin_female,
        }
    gov = db.scalars(
        select(PartyHistory).where(PartyHistory.state == state, PartyHistory.election_type == "governor").order_by(PartyHistory.position)
    ).all()

    def _gov_row(g: PartyHistory) -> dict:
        return {"name": g.politician_name, "party": g.party, "votes": g.votes, "percent": g.percent,
                "position": g.position, "running_mate": g.running_mate or None, "politician_id": g.politician_id}

    ward_count = db.scalar(select(func.count()).select_from(Ward).where(Ward.state == state))
    senators = db.scalars(select(Senator).where(Senator.state == state).order_by(Senator.district)).all()
    senate_wins = _senate_win_votes(db)
    # 2023 senatorial races (winner + losers) grouped by district, for the
    # expandable "history" under each incumbent senator.
    senate_races: dict[str, dict] = {}
    for h in db.scalars(
        select(PartyHistory).where(
            PartyHistory.state == state, PartyHistory.election_type == "senate", PartyHistory.year == "2023"
        ).order_by(PartyHistory.constituency, PartyHistory.position)
    ).all():
        d = senate_races.get(h.constituency)
        if d is None:
            short = h.constituency
            if short.lower().startswith(state.lower()):
                short = short[len(state):].strip()
            d = senate_races[h.constituency] = {"district": h.constituency, "district_short": short, "candidates": []}
        d["candidates"].append({
            "name": h.politician_name, "party": h.party, "votes": h.votes or None,
            "position": h.position, "politician_id": h.politician_id,
        })
    pres23 = db.scalar(select(StatePresidential).where(StatePresidential.state == state, StatePresidential.year == 2023))
    # politician_id per party for the 2023 national presidential tickets, so the
    # candidate names on the state page can link to their profiles.
    pres_ids = {
        h.party: h.politician_id
        for h in db.scalars(select(PartyHistory).where(
            PartyHistory.year == "2023", PartyHistory.election_type == "presidential"
        )).all()
        if h.politician_id
    }
    reps = db.scalars(select(HouseMember).where(HouseMember.state == state).order_by(HouseMember.constituency)).all()
    incumbent = db.scalar(select(Governor).where(Governor.state == state))
    gov_hist = db.scalars(select(GovernorHistory).where(GovernorHistory.state == state).order_by(GovernorHistory.seq.desc())).all()
    # 2027 declared candidates: national presidential ones (shown on every
    # state page) plus any declared specifically for this state's own race.
    declared_2027 = db.scalars(
        select(DeclaredCandidate).where(
            DeclaredCandidate.year == "2027", DeclaredCandidate.state.in_([state, "Nigeria"])
        ).order_by(DeclaredCandidate.election_type, DeclaredCandidate.party)
    ).all()
    declared_2027_pids = _declared_name_pid(db, declared_2027)
    # Our model's projected winner per race (newest model prediction wins). The
    # state map is coloured from this — blank when we have no prediction yet.
    model_prediction: dict[str, dict] = {}
    for p in preds:
        if p.source == "model" and p.election_type not in model_prediction:
            try:
                m_scores = json.loads(p.scores) if p.scores else {}
            except Exception:
                m_scores = {}
            model_prediction[p.election_type] = {"id": p.id, "party": p.leading_party, "scores": m_scores}
    return {
        "state": state,
        "facts": facts,
        "ward_count": ward_count,
        "predictions": [_public_prediction_dict(p) for p in preds],
        "model_prediction": model_prediction,
        "declared_candidates_2027": [_declared_candidate_dict(c, declared_2027_pids) for c in declared_2027],
        "politicians": [
            d for x in pols
            if _is_heavyweight(d := politician_to_dict(x, pol_assess.get(x.id, []), pol_runs.get(x.id, []), lga_names))
        ],
        "lgas": [_lga_result_dict(x) for x in lgas],
        "governor_2019": [_gov_row(g) for g in gov if g.year == "2019"],
        "governor_2023": [_gov_row(g) for g in gov if g.year == "2023"],
        "senators": [_senator_dict(s, senate_wins.get(s.politician_id)) for s in senators],
        "senate_2023": list(senate_races.values()),
        "reps": [_house_dict(m) for m in reps],
        "presidential_2023": ({
            "APC": pres23.apc, "PDP": pres23.pdp, "LP": pres23.lp, "NNPP": pres23.nnpp,
            "others": pres23.others, "total": pres23.total_votes, "turnout": pres23.turnout, "winner": pres23.winner,
            "politician_ids": pres_ids,
        } if pres23 else None),
        "governor": _governor_dict(incumbent) if incumbent else None,
        "governor_history": [
            {"name": g.name, "party": g.party, "term_start": g.term_start or None, "term_end": g.term_end or None,
             "acting": g.acting, "incumbent": g.term_end == "present", "politician_id": g.politician_id}
            for g in gov_hist
        ],
    }


@app.get("/api/states/{state}/politicians")
def state_politicians_all(state: str, db: Session = Depends(get_db)):
    """The full politician list for a state, with no heavyweight cutoff --
    backs the "view everyone" page linked from the state's heavyweight board."""
    pols = db.scalars(select(Politician).where(Politician.state == state).order_by(Politician.name)).all()
    pol_assess: dict[int, list] = defaultdict(list)
    if pols:
        for a in db.scalars(select(PoliticianAssessment).where(PoliticianAssessment.politician_id.in_([p.id for p in pols]))).all():
            pol_assess[a.politician_id].append(a)
    pol_runs = _runs_map(db, [p.id for p in pols])
    lga_names = _lga_names(db)
    return {
        "state": state,
        "politicians": [politician_to_dict(x, pol_assess.get(x.id, []), pol_runs.get(x.id, []), lga_names) for x in pols],
    }


def _governor_dict(g: Governor) -> dict:
    return {
        "name": g.name, "state": g.state, "party": g.party,
        "party_elected": g.party_elected or None,
        "term_start": g.term_start or None, "term_end": g.term_end or None,
        "politician_id": g.politician_id,
    }


def _senate_win_votes(db: Session) -> dict[int, dict]:
    """politician_id -> {votes, constituency} for their winning 2023 Senate run.
    Used to show how many votes each sitting senator polled (where Wikipedia had it)."""
    out: dict[int, dict] = {}
    for h in db.scalars(
        select(PartyHistory).where(
            PartyHistory.election_type == "senate", PartyHistory.year == "2023", PartyHistory.position == 1
        )
    ).all():
        if h.politician_id and h.votes:
            out[h.politician_id] = {"votes": h.votes, "constituency": h.constituency or None}
    return out


def _senator_dict(s: Senator, win: dict | None = None) -> dict:
    return {
        "id": s.id, "name": s.name, "state": s.state, "district": s.district, "party": s.party,
        "gender": s.gender or None, "age": s.age, "terms": s.terms,
        "leadership": s.leadership or None, "politician_id": s.politician_id,
        "votes_2023": (win or {}).get("votes"),
        "constituency": (win or {}).get("constituency"),
    }


@app.get("/api/senators")
def list_senators(db: Session = Depends(get_db)):
    rows = db.scalars(select(Senator).order_by(Senator.state, Senator.district)).all()
    wins = _senate_win_votes(db)
    return [_senator_dict(s, wins.get(s.politician_id)) for s in rows]


@app.get("/api/governors")
def list_governors(db: Session = Depends(get_db)):
    rows = db.scalars(select(Governor).order_by(Governor.state)).all()
    return [_governor_dict(g) for g in rows]


@app.get("/api/elections/presidential/2019")
def presidential_2019_results(db: Session = Depends(get_db)):
    """The official 2019 presidential result — all 73 candidates + INEC summary."""
    rows = db.scalars(
        select(PartyHistory).where(
            PartyHistory.year == "2019", PartyHistory.election_type == "presidential"
        ).order_by(PartyHistory.position)
    ).all()
    summary = {}
    try:
        summary = json.loads((_ELECTIONS_DIR / "presidential_2019.json").read_text(encoding="utf-8")).get("summary", {})
    except Exception:
        pass
    return {
        "year": 2019,
        "summary": summary,
        "candidates": [
            {"name": r.politician_name, "party": r.party, "votes": r.votes, "percent": r.percent,
             "position": r.position, "politician_id": r.politician_id, "elected": r.position == 1}
            for r in rows
        ],
    }


# ============================================================================
# Party pages — what each party has achieved, from the historical results
# ============================================================================
def _scores(r: ElectionResult) -> dict:
    try:
        return {k: int(v) for k, v in json.loads(r.scores or "{}").items()}
    except Exception:
        return {}


def _national_pres_winners(db: Session) -> dict[int, tuple[str, str]]:
    """year -> (winning party, winner name) for the presidency."""
    by_year: dict[int, dict] = defaultdict(lambda: defaultdict(int))
    national: dict[int, tuple[str, str]] = {}
    for r in db.scalars(select(ElectionResult).where(ElectionResult.office == "presidential")).all():
        sc = _scores(r)
        if r.state == "Nigeria":
            if r.winner_party:
                national[r.year] = (r.winner_party, r.winner_name)
        else:
            for p, v in sc.items():
                if p != "OTHERS":
                    by_year[r.year][p] += v
    winners: dict[int, tuple[str, str]] = {}
    for year in set(list(by_year) + list(national)):
        if year in national:
            winners[year] = national[year]
        else:
            sc = by_year.get(year, {})
            if sc:
                winners[year] = (max(sc, key=lambda p: sc[p]), "")
    return winners


@app.get("/api/parties/history")
def parties_history(db: Session = Depends(get_db)):
    """Every party that appears in the historical results, with headline counts."""
    rows = db.scalars(select(ElectionResult)).all()
    agg: dict[str, dict] = defaultdict(lambda: {"gov": 0, "pres_states": 0, "years": set()})
    for r in rows:
        for p in _scores(r):
            if p != "OTHERS":
                agg[p]["years"].add(r.year)
        if r.winner_party and r.winner_party != "OTHERS":
            if r.office == "governor":
                agg[r.winner_party]["gov"] += 1
            elif r.state != "Nigeria":
                agg[r.winner_party]["pres_states"] += 1
    nat = _national_pres_winners(db)
    nat_counts: dict[str, int] = defaultdict(int)
    for _, (wp, _n) in nat.items():
        if wp:
            nat_counts[wp] += 1
    out = []
    for acr, d in agg.items():
        out.append({
            "acronym": acr, "name": PARTY_NAMES.get(acr, acr),
            "gov_wins": d["gov"], "pres_state_wins": d["pres_states"],
            "pres_national_wins": nat_counts.get(acr, 0),
            "first_year": min(d["years"]) if d["years"] else None,
            "last_year": max(d["years"]) if d["years"] else None,
        })
    out.sort(key=lambda x: (-(x["pres_national_wins"] * 1000 + x["gov_wins"] * 10 + x["pres_state_wins"]), x["acronym"]))
    return out


@app.get("/api/parties/{acronym}/summary")
def party_summary(acronym: str, db: Session = Depends(get_db)):
    acr = acronym.strip().upper()
    rows = db.scalars(select(ElectionResult)).all()
    gov_wins: list[dict] = []
    pres_states: dict[int, list[str]] = defaultdict(list)
    gov_votes = pres_votes = 0
    years: set[int] = set()
    for r in rows:
        sc = _scores(r)
        if acr in sc:
            years.add(r.year)
        if r.office == "governor":
            gov_votes += sc.get(acr, 0)
            if r.winner_party == acr:
                gov_wins.append({"year": r.year, "state": r.state, "name": r.winner_name})
        else:
            pres_votes += sc.get(acr, 0)
            if r.state != "Nigeria" and r.winner_party == acr:
                pres_states[r.year].append(r.state)
    nat = _national_pres_winners(db)
    pres_national = sorted(
        [{"year": y, "name": nm} for y, (wp, nm) in nat.items() if wp == acr],
        key=lambda x: x["year"],
    )
    gov_wins.sort(key=lambda x: (-x["year"], x["state"]))
    return {
        "acronym": acr,
        "name": PARTY_NAMES.get(acr, acr),
        "gov_wins": gov_wins,
        "gov_win_count": len(gov_wins),
        "gov_states": sorted({g["state"] for g in gov_wins}),
        "pres_state_wins": [{"year": y, "states": sorted(s)} for y, s in sorted(pres_states.items(), reverse=True)],
        "pres_state_win_count": sum(len(s) for s in pres_states.values()),
        "pres_national_wins": pres_national,
        "total_gov_votes": gov_votes,
        "total_pres_votes": pres_votes,
        "years_active": sorted(years),
        "first_year": min(years) if years else None,
        "last_year": max(years) if years else None,
    }


def _house_dict(m: HouseMember) -> dict:
    return {"id": m.id, "state": m.state, "constituency": m.constituency, "name": m.name,
            "party": m.party, "politician_id": m.politician_id}


@app.get("/api/reps")
def list_reps(db: Session = Depends(get_db)):
    rows = db.scalars(select(HouseMember).order_by(HouseMember.state, HouseMember.constituency)).all()
    return [_house_dict(m) for m in rows]


@app.get("/api/states/{state}/wards")
def state_wards(state: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(Ward).where(Ward.state == state).order_by(Ward.lga, Ward.ward)).all()
    return [{"lga": w.lga, "ward": w.ward, "latitude": w.latitude, "longitude": w.longitude} for w in rows]


@app.get("/api/states/{state}/pu-wards")
def state_pu_wards(state: str, db: Session = Depends(get_db)):
    """Wards (from polling-unit data) with polling-unit counts and registered totals."""
    rows = db.execute(
        select(
            PollingUnit.lga,
            PollingUnit.ward,
            PollingUnit.ward_code,
            func.count().label("pu"),
            func.sum(PollingUnit.registered_voters).label("reg"),
        )
        .where(PollingUnit.state == state)
        .group_by(PollingUnit.lga, PollingUnit.ward, PollingUnit.ward_code)
        .order_by(PollingUnit.lga, PollingUnit.ward)
    ).all()
    wr = {w.ward_code: w for w in db.scalars(select(WardResult).where(WardResult.state == state)).all()}
    out = []
    for r in rows:
        w = wr.get(r.ward_code)
        out.append({
            "lga": r.lga, "ward": r.ward, "ward_code": r.ward_code, "pu_count": r.pu,
            "registered_voters": int(r.reg) if r.reg else None,
            "winner": w.winner if w else "", "runner_up": w.runner_up if w else "",
        })
    return out


def _pu_scores(p: PollingUnit) -> dict:
    return {"APC": p.votes_apc, "LP": p.votes_lp, "PDP": p.votes_pdp, "NNPP": p.votes_nnpp}


@app.get("/api/wards/{ward_code}/polling-units")
def ward_polling_units(ward_code: str, db: Session = Depends(get_db)):
    code = ward_code.replace("-", "/")
    rows = db.scalars(select(PollingUnit).where(PollingUnit.ward_code == code).order_by(PollingUnit.pu_code)).all()
    if not rows:
        return {"state": "", "lga": "", "ward": "", "ward_code": code, "result": None, "polling_units": []}
    first = rows[0]
    wr = db.scalar(select(WardResult).where(WardResult.ward_code == code))
    result = None
    if wr is not None:
        result = {
            "winner": wr.winner, "runner_up": wr.runner_up, "total_votes": wr.total_votes,
            "scores": {"APC": wr.votes_apc, "LP": wr.votes_lp, "PDP": wr.votes_pdp, "NNPP": wr.votes_nnpp},
        }
    return {
        "state": first.state,
        "lga": first.lga,
        "ward": first.ward,
        "ward_code": code,
        "result": result,
        "polling_units": [
            {
                "pu_name": p.pu_name, "pu_code": p.pu_code, "registered_voters": p.registered_voters,
                "known_votes": p.known_votes, "winner": p.winner, "runner_up": p.runner_up, "scores": _pu_scores(p),
            }
            for p in rows
        ],
    }


# --- politicians (public list + detail; logged-in submissions) ---
@app.get("/api/politicians")
def list_politicians(db: Session = Depends(get_db)):
    pols = db.scalars(select(Politician).order_by(Politician.state, Politician.name)).all()
    by_pol: dict[int, list] = defaultdict(list)
    for a in db.scalars(select(PoliticianAssessment)).all():
        by_pol[a.politician_id].append(a)
    runs = _runs_map(db, [p.id for p in pols])
    lga_names = _lga_names(db)
    dicts = [politician_to_dict(p, by_pol.get(p.id, []), runs.get(p.id, []), lga_names) for p in pols]
    return [d for d in dicts if _is_heavyweight(d)]


@app.get("/api/politicians/{pid}")
def politician_detail(pid: int, db: Session = Depends(get_db)):
    p = db.get(Politician, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="politician not found")
    assessments = db.scalars(
        select(PoliticianAssessment).where(PoliticianAssessment.politician_id == pid).order_by(PoliticianAssessment.created_at.desc())
    ).all()
    ph = db.scalars(
        select(PartyHistory).where(PartyHistory.politician_id == pid).order_by(PartyHistory.year.desc(), PartyHistory.position)
    ).all()
    lga_names = _lga_names(db)
    d = politician_to_dict(p, assessments, ph, lga_names)
    d["assessment_list"] = [
        {
            "author_name": a.author_name,
            "electoral_value": a.electoral_value,
            "influential_lgas": [n for n in (_lga_label(v, lga_names) for v in _load_list(a.influential_lgas)) if n],
            "reason": a.reason,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in assessments
    ]
    d["party_history"] = [
        {"party": h.party, "state": h.state, "year": h.year, "election_type": h.election_type,
         "votes": h.votes, "percent": h.percent, "position": h.position, "running_mate": h.running_mate or None,
         "constituency": h.constituency or None}
        for h in ph
    ]
    d["presidential_state_votes"] = _presidential_state_votes(db, ph)
    return d


@app.post("/api/politicians/{pid}/photo", status_code=201)
def submit_politician_photo(pid: int, payload: PhotoSubmitIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Politician, pid) is None:
        raise HTTPException(status_code=404, detail="politician not found")
    img = payload.image.strip()
    if not img.startswith("data:image/"):
        raise HTTPException(status_code=422, detail="expected an image data URL")
    db.add(PoliticianPhoto(politician_id=pid, user_id=user.id, author_name=user.full_name or user.email, image=img, status="pending"))
    db.commit()
    return {"ok": True, "status": "pending"}


def _resolve_lga_ids(db: Session, state: str, values: list) -> list[int]:
    """Map submitted LGA names (or ids) to canonical LGA ids within a state, so we
    never store a name — a later rename of the LGA propagates automatically."""
    rows = db.scalars(select(Lga).where(Lga.state == state)).all()
    by_norm = {_lga_norm(l.name): l.id for l in rows}
    ids: list[int] = []
    for v in values:
        if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
            vid = int(v)
            if any(l.id == vid for l in rows):
                ids.append(vid)
            continue
        nv = _lga_norm(str(v))
        if not nv:
            continue
        mid = by_norm.get(nv)
        if mid is None:  # tolerate partial / prefix entries
            for norm, lid in by_norm.items():
                if len(nv) >= 4 and (norm.startswith(nv) or nv.startswith(norm)):
                    mid = lid
                    break
        if mid is not None and mid not in ids:
            ids.append(mid)
    return ids[:20]


@app.post("/api/politicians/{pid}/assessment", status_code=201)
def submit_politician_assessment(pid: int, payload: AssessmentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    pol = db.get(Politician, pid)
    if pol is None:
        raise HTTPException(status_code=404, detail="politician not found")
    lga_ids = _resolve_lga_ids(db, pol.state, list(payload.influential_lgas))
    db.add(PoliticianAssessment(
        politician_id=pid, user_id=user.id, author_name=user.full_name or user.email,
        electoral_value=int(payload.electoral_value), influential_lgas=json.dumps(lga_ids), reason=payload.reason or "",
    ))
    db.commit()
    return {"ok": True}


# --- analyses (contributor per-party projections) ---
def _current_week() -> str:
    t = date.today()
    return (t - timedelta(days=t.weekday())).isoformat()


def analysis_to_dict(a: Analysis) -> dict:
    try:
        scores = json.loads(a.scores) if a.scores else {}
    except Exception:
        scores = {}
    return {
        "id": a.id,
        "contributor_name": a.contributor_name,
        "contributor_email": a.contributor_email,
        "election_type": a.election_type,
        "state": a.state,
        "lga": a.lga,
        "senatorial_district": a.senatorial_district,
        "leading_party": a.leading_party,
        "scores": scores,
        "notes": a.notes,
        "measurement_week": a.measurement_week,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@app.post("/api/analyses", status_code=201)
def create_analysis(payload: AnalysisIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    scores = {str(k): float(v) for k, v in payload.scores.items() if v is not None}
    leading = max(scores, key=lambda p: scores[p]) if scores else ""
    a = Analysis(
        user_id=user.id,
        contributor_name=user.full_name,
        contributor_email=user.email,
        election_type=payload.election_type,
        state=payload.state,
        lga=payload.lga or "",
        senatorial_district=payload.senatorial_district or "",
        leading_party=leading,
        scores=json.dumps(scores),
        notes=payload.notes or "",
        measurement_week=_current_week(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return analysis_to_dict(a)


@app.get("/api/analyses/mine")
def my_analyses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Analysis).where(Analysis.user_id == user.id).order_by(Analysis.created_at.desc())).all()
    return [analysis_to_dict(a) for a in rows]


# --- shared predictions board (logged-in view; owner/admin edit) ---
def _can_edit_pred(user: User, p: StatePrediction) -> bool:
    return bool(user.is_admin or (p.user_id is not None and p.user_id == user.id))


def state_prediction_to_dict(p: StatePrediction, user: User) -> dict:
    try:
        scores = json.loads(p.scores) if p.scores else {}
    except Exception:
        scores = {}
    return {
        "id": p.id,
        "state": p.state,
        "election_type": p.election_type,
        "source": p.source,
        "label": p.label,
        "author_name": p.author_name,
        "leading_party": p.leading_party,
        "scores": scores,
        "notes": p.notes,
        "year": p.year,
        "scenario_id": p.scenario_id,
        "has_detail": bool(p.source == "model" and p.detail and p.detail != "{}"),
        "is_mine": bool(p.user_id is not None and p.user_id == user.id),
        "can_edit": _can_edit_pred(user, p),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# States with off-cycle governorship terms (different year than the main
# 31-state cycle) plus FCT, which has no governorship at all.
OFF_CYCLE_GOVERNOR_STATES = {"Anambra", "Edo", "Ekiti", "Ondo", "Osun", "FCT"}
GOVERNOR_2027_STATES = [s for s in STATE_NAMES if s not in OFF_CYCLE_GOVERNOR_STATES]


def _norm_name(s: str) -> str:
    return " ".join((s or "").lower().split())


def _declared_name_pid(db: Session, rows: list[DeclaredCandidate]) -> dict[str, int]:
    """normalized politician_name -> politician_id, for declared candidates that
    have no stored id (e.g. added by name only), so the candidate names can still
    link to a profile. When a name matches several politicians (e.g. a national
    figure and a same-named minor candidate) the most prominent one — by most votes
    ever pulled — wins; a name that matches only namesakes with no votes is skipped."""
    names = {_norm_name(r.politician_name) for r in rows if r.politician_id is None and r.politician_name}
    if not names:
        return {}
    cands: dict[str, list[int]] = defaultdict(list)
    for pid, name in db.execute(select(Politician.id, Politician.name)).all():
        n = _norm_name(name)
        if n in names:
            cands[n].append(pid)
    if not cands:
        return {}
    all_ids = [pid for ids in cands.values() for pid in ids]
    votes: dict[int, int] = defaultdict(int)
    for pid, mx in db.execute(
        select(PartyHistory.politician_id, func.max(PartyHistory.votes))
        .where(PartyHistory.politician_id.in_(all_ids), PartyHistory.election_type != "primary")
        .group_by(PartyHistory.politician_id)
    ).all():
        if pid is not None:
            votes[pid] = mx or 0
    out: dict[str, int] = {}
    for n, ids in cands.items():
        if len(ids) == 1:
            out[n] = ids[0]
            continue
        best = max(ids, key=lambda i: votes.get(i, 0))
        if votes.get(best, 0) > 0:  # don't guess between namesakes that never polled
            out[n] = best
    return out


def _declared_candidate_dict(c: DeclaredCandidate, name_pid: dict[str, int] | None = None) -> dict:
    pid = c.politician_id
    if pid is None and name_pid:
        pid = name_pid.get(_norm_name(c.politician_name))
    return {
        "id": c.id, "state": c.state, "election_type": c.election_type, "year": c.year,
        "party": c.party, "politician_name": c.politician_name, "politician_id": pid,
        "running_mate": c.running_mate or None,
    }


@app.get("/api/declared-candidates")
def list_declared_candidates(
    election_type: str | None = None, year: str = "2027", state: str | None = None, db: Session = Depends(get_db),
):
    q = select(DeclaredCandidate).where(DeclaredCandidate.year == year)
    if election_type:
        q = q.where(DeclaredCandidate.election_type == election_type)
    if state:
        q = q.where(DeclaredCandidate.state == state)
    rows = db.scalars(q.order_by(DeclaredCandidate.state, DeclaredCandidate.party)).all()
    name_pid = _declared_name_pid(db, rows)
    return [_declared_candidate_dict(c, name_pid) for c in rows]


@app.get("/api/declared-candidates/governor-states")
def declared_candidate_governor_states(year: str = "2027"):
    """Which states actually hold a governor election in `year` (main 31-state
    cycle only, for now) -- backs the admin dropdown so off-cycle states can't
    be mis-entered."""
    return {"year": year, "states": GOVERNOR_2027_STATES}


@app.post("/api/admin/declared-candidates", status_code=201)
def admin_add_declared_candidate(payload: DeclaredCandidateIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.election_type == "governor" and payload.year == "2027" and payload.state not in GOVERNOR_2027_STATES:
        raise HTTPException(status_code=400, detail=f"{payload.state} does not hold a governor election in 2027 (off-cycle)")
    pol = db.get(Politician, payload.politician_id) if payload.politician_id else None
    row = DeclaredCandidate(
        state=payload.state, election_type=payload.election_type, year=payload.year,
        party=payload.party.strip().upper(), politician_name=(pol.name if pol else payload.politician_name),
        politician_id=pol.id if pol else None, running_mate=payload.running_mate,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _declared_candidate_dict(row)


@app.delete("/api/admin/declared-candidates/{cid}")
def admin_delete_declared_candidate(cid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(DeclaredCandidate, cid)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"ok": True}


@app.get("/api/board/states")
def board_states(user: User = Depends(current_user), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(StatePrediction.state, func.count()).group_by(StatePrediction.state)).all())
    return [{"state": s, "count": counts.get(s, 0)} for s in STATE_NAMES]


@app.get("/api/board/states/{state}")
def board_state_predictions(state: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(StatePrediction).where(StatePrediction.state == state).order_by(StatePrediction.source, StatePrediction.created_at.desc())
    ).all()
    return [state_prediction_to_dict(p, user) for p in rows]


@app.post("/api/board/predictions", status_code=201)
def board_add_prediction(payload: StatePredictionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    scores = {str(k): float(v) for k, v in payload.scores.items() if v is not None}
    leading = max(scores, key=lambda p: scores[p]) if scores else ""
    source = payload.source or "expert"
    if source == "past_performance" and not user.is_admin:
        source = "expert"  # only admins may post past performance
    is_pp = source == "past_performance"
    p = StatePrediction(
        user_id=None if is_pp else user.id,
        author_name="Past performance" if is_pp else (user.full_name or user.email),
        author_email="" if is_pp else user.email,
        state=payload.state,
        election_type=payload.election_type,
        source=source,
        label=payload.label or "",
        leading_party=leading,
        scores=json.dumps(scores),
        notes=payload.notes or "",
        year="2023" if is_pp else "2027",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return state_prediction_to_dict(p, user)


@app.put("/api/board/predictions/{pid}")
def board_edit_prediction(pid: int, payload: StatePredictionUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(StatePrediction, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    if not _can_edit_pred(user, p):
        raise HTTPException(status_code=403, detail="not allowed to edit this prediction")
    data = payload.model_dump(exclude_unset=True)
    if data.get("scores") is not None:
        scores = {str(k): float(v) for k, v in data["scores"].items() if v is not None}
        p.scores = json.dumps(scores)
        p.leading_party = max(scores, key=lambda q: scores[q]) if scores else ""
    if data.get("election_type"):
        p.election_type = data["election_type"]
    if "notes" in data and data["notes"] is not None:
        p.notes = data["notes"]
    if "label" in data and data["label"] is not None:
        p.label = data["label"]
    db.commit()
    db.refresh(p)
    return state_prediction_to_dict(p, user)


@app.delete("/api/board/predictions/{pid}")
def board_delete_prediction(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(StatePrediction, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    if not _can_edit_pred(user, p):
        raise HTTPException(status_code=403, detail="not allowed to delete this prediction")
    db.delete(p)
    db.commit()
    return {"ok": True}


# --- public: full detail of a single prediction (powers the click-through view) ---
@app.get("/api/predictions/{pid}")
def prediction_detail(pid: int, db: Session = Depends(get_db)):
    p = db.get(StatePrediction, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    try:
        scores = json.loads(p.scores) if p.scores else {}
    except Exception:
        scores = {}
    try:
        detail = json.loads(p.detail) if p.detail else {}
    except Exception:
        detail = {}
    scenario = db.get(PredictionScenario, p.scenario_id) if p.scenario_id else None
    return {
        "id": p.id,
        "state": p.state,
        "election_type": p.election_type,
        "source": p.source,
        "label": p.label,
        "author_name": p.author_name,
        "leading_party": p.leading_party,
        "scores": scores,
        "notes": p.notes,
        "year": p.year,
        "detail": detail,
        "scenario": (
            {"id": scenario.id, "name": scenario.name, "description": scenario.description,
             "target_year": scenario.target_year, "election_type": scenario.election_type}
            if scenario else None
        ),
    }


# ============================================================================
# Admin: the prediction model (scenarios → resumable background jobs)
# ============================================================================
def _scenario_progress(s: PredictionScenario) -> dict:
    try:
        log = json.loads(s.log) if s.log else []
    except Exception:
        log = []
    pct = round(100 * s.cursor / s.total) if s.total else 0
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "election_type": s.election_type,
        "target_year": s.target_year,
        "status": s.status,
        "cursor": s.cursor,
        "total": s.total,
        "percent": pct,
        "message": s.message,
        "log": log,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _scenario_politician_dict(p: ScenarioPolitician) -> dict:
    return {
        "id": p.id,
        "politician_id": p.politician_id,
        "politician_name": p.politician_name,
        "new_party": p.new_party,
        "delta_popularity": p.delta_popularity,
        "influence_pct": p.influence_pct,
        "scope": p.scope,
        "home_state": p.home_state,
    }


def _scenario_trend_dict(t: ScenarioTrend) -> dict:
    try:
        states = json.loads(t.scope_states) if t.scope_states else []
    except Exception:
        states = []
    return {"id": t.id, "name": t.name, "shift_pct": t.shift_pct, "target_party": t.target_party, "scope_states": states}


def _scenario_full(s: PredictionScenario, db: Session) -> dict:
    d = _scenario_progress(s)
    pols = db.scalars(select(ScenarioPolitician).where(ScenarioPolitician.scenario_id == s.id).order_by(ScenarioPolitician.id)).all()
    trends = db.scalars(select(ScenarioTrend).where(ScenarioTrend.scenario_id == s.id).order_by(ScenarioTrend.id)).all()
    d["politicians"] = [_scenario_politician_dict(p) for p in pols]
    d["trends"] = [_scenario_trend_dict(t) for t in trends]
    return d


@app.get("/api/admin/scenarios")
def admin_scenarios(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(PredictionScenario).order_by(PredictionScenario.created_at.desc())).all()
    return [_scenario_progress(s) for s in rows]


@app.post("/api/admin/scenarios", status_code=201)
def admin_create_scenario(payload: ScenarioIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = PredictionScenario(
        name=payload.name,
        description=payload.description or "",
        election_type=payload.election_type or "presidential",
        created_by=user.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _scenario_full(s, db)


@app.get("/api/admin/scenarios/{sid}")
def admin_scenario(sid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(PredictionScenario, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    return _scenario_full(s, db)


@app.delete("/api/admin/scenarios/{sid}")
def admin_delete_scenario(sid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(PredictionScenario, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    s.status = "paused"  # signal any running worker to stop
    db.commit()
    db.execute(delete(ScenarioPolitician).where(ScenarioPolitician.scenario_id == sid))
    db.execute(delete(ScenarioTrend).where(ScenarioTrend.scenario_id == sid))
    db.execute(delete(StatePrediction).where(StatePrediction.scenario_id == sid))
    db.delete(s)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/scenarios/{sid}/politicians", status_code=201)
def admin_scenario_add_politician(sid: int, payload: ScenarioPoliticianIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(PredictionScenario, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    pol = db.get(Politician, payload.politician_id)
    if pol is None:
        raise HTTPException(status_code=404, detail="politician not found")
    row = ScenarioPolitician(
        scenario_id=sid,
        politician_id=pol.id,
        politician_name=pol.name,
        new_party=payload.new_party.strip().upper(),
        delta_popularity=payload.delta_popularity,
        influence_pct=payload.influence_pct,
        scope=payload.scope if payload.scope in ("local", "national", "election") else "local",
        home_state=pol.state,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _scenario_politician_dict(row)


@app.delete("/api/admin/scenario-politicians/{rid}")
def admin_scenario_remove_politician(rid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(ScenarioPolitician, rid)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"ok": True}


@app.post("/api/admin/scenarios/{sid}/trends", status_code=201)
def admin_scenario_add_trend(sid: int, payload: ScenarioTrendIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(PredictionScenario, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    row = ScenarioTrend(
        scenario_id=sid,
        name=payload.name,
        shift_pct=payload.shift_pct,
        target_party=payload.target_party.strip().upper(),
        scope_states=json.dumps([st for st in payload.scope_states if st]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _scenario_trend_dict(row)


@app.delete("/api/admin/scenario-trends/{rid}")
def admin_scenario_remove_trend(rid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(ScenarioTrend, rid)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"ok": True}


@app.post("/api/admin/scenarios/{sid}/run")
def admin_scenario_run(sid: int, restart: bool = False, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(PredictionScenario, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    if restart or s.status in ("done", "error"):
        s.cursor = 0  # start over
        s.log = "[]"
    s.status = "running"
    s.message = "Queued…"
    db.commit()
    prediction_worker.start_scenario(sid)
    return _scenario_progress(s)


@app.post("/api/admin/scenarios/{sid}/pause")
def admin_scenario_pause(sid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(PredictionScenario, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    if s.status == "running":
        s.status = "paused"
        s.message = f"Paused at {s.cursor}/{s.total}."
        db.commit()
    return _scenario_progress(s)


@app.get("/api/admin/scenarios/{sid}/status")
def admin_scenario_status(sid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(PredictionScenario, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    return _scenario_progress(s)


@app.get("/api/admin/politician-search")
def admin_politician_search(q: str = "", _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = select(Politician).order_by(Politician.name)
    term = q.strip()
    if term:
        query = query.where(Politician.name.ilike(f"%{term}%"))
    rows = db.scalars(query.limit(25)).all()
    return [{"id": p.id, "name": p.name, "state": p.state, "party": p.party, "title": p.title} for p in rows]


@app.get("/api/admin/politician-info/{pid}")
def admin_politician_info(pid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    pol = db.get(Politician, pid)
    if pol is None:
        raise HTTPException(status_code=404, detail="politician not found")
    runs = db.scalars(
        select(PartyHistory).where(PartyHistory.politician_id == pid).order_by(PartyHistory.year.desc())
    ).all()
    run_dicts = [
        {"year": r.year, "election_type": r.election_type, "party": r.party, "state": r.state,
         "votes": r.votes, "percent": r.percent, "constituency": r.constituency}
        for r in runs
    ]
    # suggest an influence % from his best recorded vote share (primaries excluded)
    shares = [r.percent for r in runs if r.percent and r.election_type != "primary"]
    suggested = round(max(shares)) if shares else 0
    return {
        "id": pol.id,
        "name": pol.name,
        "state": pol.state,
        "party": pol.party,
        "title": pol.title,
        "aka": _load_list(pol.aka),
        "runs": run_dicts,
        "suggested_influence_pct": suggested,
        "current_party": pol.party or "",
    }


# --- auth ---
@app.post("/auth/google")
def auth_google(payload: GoogleAuthIn, db: Session = Depends(get_db)):
    info = verify_google_credential(payload.credential)
    sub = info["sub"]
    email = (info.get("email") or "").strip()

    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None and email:
        user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(google_sub=sub, email=email)
        db.add(user)

    user.google_sub = sub
    user.email = email
    user.email_verified = bool(info.get("email_verified"))
    user.full_name = info.get("name") or user.full_name or ""
    user.given_name = info.get("given_name")
    user.family_name = info.get("family_name")
    user.picture = info.get("picture")
    user.locale = info.get("locale")
    if email.lower() in _admin_emails():
        user.is_admin = True
    user.last_login_at = datetime.now(timezone.utc)

    # Promote a matching interested user (homepage form) into this account, pre-filling
    # any details they entered, then remove them from the interested list.
    if email:
        interested = db.scalar(select(InterestedUser).where(func.lower(InterestedUser.email) == email.lower()))
        if interested is not None:
            if not user.full_name:
                user.full_name = interested.full_name or ""
            if not user.phone:
                user.phone = interested.mobile or None
            if not user.home_state:
                user.home_state = interested.state or None
            db.delete(interested)

    db.commit()
    db.refresh(user)
    return {"token": create_token(user), "user": user_to_dict(user)}


@app.get("/auth/me")
def auth_me(user: User = Depends(current_user)):
    return user_to_dict(user)


@app.patch("/auth/me")
def update_me(payload: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if "known_states" in data:
        data["known_states"] = json.dumps(data.get("known_states") or [])
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


# --- admin (gated) ---
@app.get("/api/admin/interested-users")
def admin_interested_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(InterestedUser).order_by(InterestedUser.created_at.desc())).all()
    return [
        {
            "id": r.id,
            "full_name": r.full_name,
            "email": r.email,
            "location": r.location,
            "state": r.state,
            "mobile": r.mobile,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.get("/api/admin/stats")
def admin_stats(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    interested = db.scalar(select(func.count()).select_from(InterestedUser))
    users = db.scalar(select(func.count()).select_from(User))
    analyses = db.scalar(select(func.count()).select_from(Analysis))
    return {"interested": interested, "users": users, "analyses": analyses}


@app.get("/api/admin/analyses")
def admin_analyses(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Analysis).order_by(Analysis.measurement_week.desc(), Analysis.created_at.desc())
    ).all()
    return [analysis_to_dict(a) for a in rows]


# --- admin: set the official predictions (with the user-trace aggregate for reference) ---
@app.get("/api/admin/predictions")
def admin_predictions(election_type: str, week: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    by_state: dict[str, dict[str, float]] = {}
    for p in db.scalars(
        select(Prediction).where(Prediction.election_type == election_type, Prediction.measurement_week == week)
    ).all():
        by_state.setdefault(p.state, {})[p.party] = p.score

    # aggregate (average) of user analyses for the same election type + week
    agg_sum: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}
    for a in db.scalars(
        select(Analysis).where(Analysis.election_type == election_type, Analysis.measurement_week == week)
    ).all():
        try:
            sc = json.loads(a.scores) if a.scores else {}
        except Exception:
            sc = {}
        counts[a.state] = counts.get(a.state, 0) + 1
        bucket = agg_sum.setdefault(a.state, {})
        for party, val in sc.items():
            bucket[party] = bucket.get(party, 0.0) + float(val)

    out = []
    for st in STATE_NAMES:
        cnt = counts.get(st, 0)
        aggregate = {p: round(v / cnt, 1) for p, v in agg_sum.get(st, {}).items()} if cnt else {}
        out.append({"state": st, "scores": by_state.get(st, {}), "aggregate": aggregate, "trace_count": cnt})
    return out


@app.put("/api/admin/predictions")
def set_prediction(payload: PredictionSetIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(
        delete(Prediction).where(
            Prediction.state == payload.state,
            Prediction.election_type == payload.election_type,
            Prediction.measurement_week == payload.week,
        )
    )
    for party, score in payload.scores.items():
        if score is None:
            continue
        db.add(
            Prediction(
                state=payload.state,
                election_type=payload.election_type,
                party=str(party),
                score=float(score),
                measurement_week=payload.week,
            )
        )
    db.commit()
    return {"ok": True, "state": payload.state}


# --- admin: politicians (add + approve submitted photos) ---
@app.post("/api/admin/politicians", status_code=201)
def admin_add_politician(payload: PoliticianIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = Politician(name=payload.name, state=payload.state, title=payload.title or "", party=payload.party or "", note=payload.note or "")
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "state": p.state}


@app.get("/api/admin/politician-photos")
def admin_pending_photos(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(PoliticianPhoto).where(PoliticianPhoto.status == "pending").order_by(PoliticianPhoto.created_at.desc())).all()
    pols = {p.id: p for p in db.scalars(select(Politician)).all()}
    return [
        {
            "id": r.id,
            "politician_id": r.politician_id,
            "politician_name": pols[r.politician_id].name if r.politician_id in pols else "?",
            "state": pols[r.politician_id].state if r.politician_id in pols else "",
            "author_name": r.author_name,
            "image": r.image,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.post("/api/admin/politician-photos/{sid}/approve")
def admin_approve_photo(sid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    sub = db.get(PoliticianPhoto, sid)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    pol = db.get(Politician, sub.politician_id)
    if pol is not None:
        pol.photo = sub.image
    sub.status = "approved"
    db.commit()
    return {"ok": True}


@app.post("/api/admin/politician-photos/{sid}/reject")
def admin_reject_photo(sid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    sub = db.get(PoliticianPhoto, sid)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    sub.status = "rejected"
    db.commit()
    return {"ok": True}


# --- admin: manage which parties are on the ballot per election type ---
@app.put("/api/admin/parties/elections")
def set_party_elections(payload: PartyElectionSetIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(delete(PartyElection).where(PartyElection.election_type == payload.election_type))
    seen: set[str] = set()
    for acr in payload.acronyms:
        a = str(acr).strip()
        if not a or a in seen:
            continue
        seen.add(a)
        db.add(PartyElection(party_acronym=a, election_type=payload.election_type))
    db.commit()
    return {"ok": True, "election_type": payload.election_type, "acronyms": sorted(seen)}


@app.get("/api/admin/users")
def admin_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).order_by(User.created_at.desc())).all()
    out = []
    for u in rows:
        d = user_to_dict(u)
        d["created_at"] = u.created_at.isoformat() if u.created_at else None
        d["last_login_at"] = u.last_login_at.isoformat() if u.last_login_at else None
        out.append(d)
    return out
