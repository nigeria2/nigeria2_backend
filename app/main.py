"""Minimal FastAPI backend for Nigeria 2.0."""
import json
import os
import pathlib
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .auth import create_token, current_user, require_admin, verify_google_credential
from .db import SessionLocal, engine, get_db
from .models import Analysis, InterestedUser, Party, PartyElection, Prediction, ProblemUnit, StatePrediction, User
from .schemas import (
    AnalysisIn,
    GoogleAuthIn,
    JoinIn,
    JoinOut,
    PartyElectionSetIn,
    PredictionSetIn,
    ProfileUpdate,
    StatePredictionIn,
    StatePredictionUpdate,
)
from .seed import (
    BASE,
    seed_analyses,
    seed_parties,
    seed_party_elections,
    seed_predictions,
    seed_problem_units,
    seed_state_predictions,
)

STATE_NAMES = sorted(BASE.keys())


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
                sp = seed_state_predictions(db)
                if sp:
                    print(f"[startup] seeded {sp} state predictions")
    except Exception as exc:
        print(f"[startup] seed error: {exc}")
    yield


app = FastAPI(title="Nigeria 2.0 API", version="0.15.0", lifespan=lifespan)

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
        "is_mine": bool(p.user_id is not None and p.user_id == user.id),
        "can_edit": _can_edit_pred(user, p),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


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
