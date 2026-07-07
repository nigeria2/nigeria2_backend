"""SQLAlchemy ORM models."""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Signup(Base):
    """A person who joined the movement via the homepage form."""

    __tablename__ = "signups"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), index=True)
    location: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(100))
    mobile: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
