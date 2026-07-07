"""SQLAlchemy ORM models."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class InterestedUser(Base):
    """A person who entered their details in the homepage form but has not yet
    completed Google sign-in. On completing sign-in they are merged into `users`
    and removed from here."""

    __tablename__ = "interested_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), index=True)
    location: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(100))
    mobile: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    """A Google-authenticated account, with full contributor profile."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # --- Google identity ---
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    given_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    family_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    picture: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- contributor profile (collected during onboarding) ---
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    year_of_birth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    home_lga: Mapped[str | None] = mapped_column(String(120), nullable=True)
    residence_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voter_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    known_states: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array (text)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- timestamps ---
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Prediction(Base):
    """Aggregated per-state projection (already crunched from raw traces).

    One row per (state, election_type, party, measurement_week).
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    election_type: Mapped[str] = mapped_column(String(20), index=True)  # presidential | governor | senate
    party: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)  # projected polling share (0-100)
    measurement_week: Mapped[str] = mapped_column(String(10), index=True)  # ISO date, e.g. 2026-07-06
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Party(Base):
    """A registered political party with its national officials."""

    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    acronym: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    chairman: Mapped[str] = mapped_column(String(200), default="")
    secretary: Mapped[str] = mapped_column(String(200), default="")
    treasurer: Mapped[str] = mapped_column(String(200), default="")
    financial_secretary: Mapped[str] = mapped_column(String(200), default="")
    legal_adviser: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartyElection(Base):
    """Which parties are relevant for which election type (presidential/governor/senate)."""

    __tablename__ = "party_elections"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_acronym: Mapped[str] = mapped_column(String(20), index=True)
    election_type: Mapped[str] = mapped_column(String(30), index=True)


class StatePrediction(Base):
    """A shared per-state prediction. Added by an expert directly, or seeded as
    past performance. Visible to all logged-in users; editable by admins (all) or
    the authoring expert (their own)."""

    __tablename__ = "state_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # owning expert; null for past-performance
    author_name: Mapped[str] = mapped_column(String(200), default="")
    author_email: Mapped[str] = mapped_column(String(255), default="")
    state: Mapped[str] = mapped_column(String(50), index=True)
    election_type: Mapped[str] = mapped_column(String(30), default="presidential")
    source: Mapped[str] = mapped_column(String(30), default="expert")  # expert | past_performance
    label: Mapped[str] = mapped_column(String(120), default="")
    leading_party: Mapped[str] = mapped_column(String(20), default="")
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON per-party shares
    notes: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[str] = mapped_column(String(10), default="2027")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LgaResult(Base):
    """Verified 2023 presidential result aggregated per LGA."""

    __tablename__ = "lga_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    lga: Mapped[str] = mapped_column(String(120))
    leading_party: Mapped[str] = mapped_column(String(20), default="")
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON per-party shares
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    year: Mapped[str] = mapped_column(String(10), default="2023")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Politician(Base):
    """A political heavyweight associated with a state."""

    __tablename__ = "politicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    party: Mapped[str] = mapped_column(String(20), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProblemUnit(Base):
    """A polling unit flagged for strong anomalies in the 2023 election."""

    __tablename__ = "problem_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    lga: Mapped[str] = mapped_column(String(120), default="")
    ward: Mapped[str] = mapped_column(String(120), default="")
    polling_unit: Mapped[str] = mapped_column(String(200), default="")
    pu_code: Mapped[str] = mapped_column(String(40), default="")
    anomaly_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="High")  # High | Medium
    description: Mapped[str] = mapped_column(Text, default="")
    registered_voters: Mapped[int] = mapped_column(Integer, default=0)
    accredited_voters: Mapped[int] = mapped_column(Integer, default=0)
    votes_cast: Mapped[int] = mapped_column(Integer, default=0)
    election_year: Mapped[str] = mapped_column(String(10), default="2023")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Analysis(Base):
    """A contributor's per-party projection for a state (feeds the aggregation)."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contributor_name: Mapped[str] = mapped_column(String(200), default="")
    contributor_email: Mapped[str] = mapped_column(String(255), default="")
    election_type: Mapped[str] = mapped_column(String(30))  # presidential | governor | senate
    state: Mapped[str] = mapped_column(String(50), index=True)
    lga: Mapped[str] = mapped_column(String(120), default="")
    senatorial_district: Mapped[str] = mapped_column(String(120), default="")
    leading_party: Mapped[str] = mapped_column(String(20), default="")  # party with the highest score
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON: {"APC": 40, "PDP": 30, ...}
    notes: Mapped[str] = mapped_column(Text, default="")
    measurement_week: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
