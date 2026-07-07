"""Minimal FastAPI backend for Nigeria 2.0."""
import pathlib
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .db import engine, get_db
from .models import Signup
from .schemas import JoinIn, JoinOut


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
    yield


app = FastAPI(title="Nigeria 2.0 API", version="0.4.0", lifespan=lifespan)

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


@app.get("/")
def root():
    return {"service": "nigeria2-backend", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/hello")
def hello(name: str = "Nigeria"):
    return {"message": f"Hello, {name}!"}


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


@app.get("/api/join/count")
def join_count(db: Session = Depends(get_db)):
    return {"count": db.scalar(select(func.count()).select_from(Signup))}
