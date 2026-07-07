"""Database engine, session factory and declarative base."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def normalize_url(url: str) -> str:
    """Coerce a Coolify/Postgres URL to the psycopg 3 driver SQLAlchemy expects."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Engine/session are None when DATABASE_URL is unset so the app can still boot
# (e.g. for /health) instead of crashing on import.
engine = create_engine(normalize_url(DATABASE_URL), pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False) if engine else None


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a scoped database session."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
