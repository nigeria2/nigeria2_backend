"""Minimal FastAPI backend for Nigeria 2.0."""
import json
import os
import pathlib
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .auth import create_token, current_user, require_admin, verify_google_credential
from .db import SessionLocal, engine, get_db
from .models import Analysis, Prediction, Signup, User
from .schemas import AnalysisIn, GoogleAuthIn, JoinIn, JoinOut, PredictionSetIn, ProfileUpdate
from .seed import BASE, seed_analyses, seed_predictions

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
    except Exception as exc:
        print(f"[startup] seed error: {exc}")
    yield


app = FastAPI(title="Nigeria 2.0 API", version="0.9.0", lifespan=lifespan)

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


# --- public: join the movement ---
@app.post("/api/join", response_model=JoinOut, status_code=201)
def join(payload: JoinIn, db: Session = Depends(get_db)):
    rec = Signup(
        full_name=payload.full_name,
        email=payload.email,
        location=payload.location,
        state=payload.state,
        mobile=payload.mobile,
    )
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
@app.get("/api/admin/signups")
def admin_signups(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Signup).order_by(Signup.created_at.desc())).all()
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
    signups = db.scalar(select(func.count()).select_from(Signup))
    users = db.scalar(select(func.count()).select_from(User))
    analyses = db.scalar(select(func.count()).select_from(Analysis))
    return {"signups": signups, "users": users, "analyses": analyses}


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
