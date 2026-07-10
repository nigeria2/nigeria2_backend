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
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
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
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    election_type: Mapped[str] = mapped_column(String(30), default="presidential")
    source: Mapped[str] = mapped_column(String(30), default="expert")  # expert | past_performance
    label: Mapped[str] = mapped_column(String(120), default="")
    leading_party: Mapped[str] = mapped_column(String(20), default="")
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON per-party shares
    notes: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[str] = mapped_column(String(10), default="2027")
    # When source == "model": the scenario that generated this row and a JSON
    # trace of exactly how the projection was computed (for the details view).
    scenario_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    detail: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PredictionScenario(Base):
    """A named set of assumptions that a background job turns into a full set of
    per-state model predictions. The job is resumable: `cursor` records how many
    states have been processed, so a killed job resumes from where it stopped."""

    __tablename__ = "prediction_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    election_type: Mapped[str] = mapped_column(String(30), default="presidential")
    base_year: Mapped[str] = mapped_column(String(10), default="2023")
    target_year: Mapped[str] = mapped_column(String(10), default="2027")
    # draft | running | paused | done | error
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    cursor: Mapped[int] = mapped_column(Integer, default=0)  # states processed so far
    total: Mapped[int] = mapped_column(Integer, default=0)  # states to process
    message: Mapped[str] = mapped_column(String(300), default="")
    log: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of progress lines
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ScenarioPolitician(Base):
    """A politician's assumed influence within a scenario. His historical votes in
    the elections he ran get re-allocated to his `new_party`, scaled by his
    `delta_popularity` (how popular he is now vs his last run) and `influence_pct`
    (the share of the vote pool he can swing)."""

    __tablename__ = "scenario_politicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(Integer, index=True)
    politician_id: Mapped[int] = mapped_column(Integer, index=True)
    politician_name: Mapped[str] = mapped_column(String(200), default="")
    new_party: Mapped[str] = mapped_column(String(20), default="")
    delta_popularity: Mapped[float] = mapped_column(Float, default=0.0)  # signed %, e.g. +20 / -10
    influence_pct: Mapped[float] = mapped_column(Float, default=0.0)  # % of the vote pool he swings
    scope: Mapped[str] = mapped_column(String(20), default="local")  # local | national | election
    home_state: Mapped[str] = mapped_column(String(50), default="")


class ElectionResult(Base):
    """A historical election result for one state (or 'Nigeria' national), one office,
    one year — the party→votes tally, plus the winner. Backs the party pages."""

    __tablename__ = "election_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    office: Mapped[str] = mapped_column(String(20), index=True)  # presidential | governor
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON {PARTY: votes}
    registered_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_party: Mapped[str] = mapped_column(String(20), index=True, default="")
    winner_name: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(40), default="")


class ScenarioTrend(Base):
    """A free-form popularity trend within a scenario (e.g. "Christian vote"): it
    shifts `shift_pct` of a state's votes toward `target_party`. Optionally scoped
    to a subset of states (JSON list); empty = all states."""

    __tablename__ = "scenario_trends"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    shift_pct: Mapped[float] = mapped_column(Float, default=0.0)
    target_party: Mapped[str] = mapped_column(String(20), default="")
    scope_states: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of state names; empty = all


class State(Base):
    """Canonical state reference with facts and statistics."""

    __tablename__ = "states"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    geo_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(10), default="")
    capital: Mapped[str] = mapped_column(String(80), default="")
    area_sq_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    census_1991: Mapped[int | None] = mapped_column(Integer, nullable=True)
    census_2006: Mapped[int | None] = mapped_column(Integer, nullable=True)
    population_projection: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_phone_2021: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_phone_2020: Mapped[int | None] = mapped_column(Integer, nullable=True)
    newly_registered_voters_2022: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voters_presidential_2019: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buhari_votes_2019: Mapped[int | None] = mapped_column(Integer, nullable=True)
    atiku_votes_2019: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_votes_2019: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes_2023: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nin_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nin_male: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nin_female: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PartyHistory(Base):
    """A politician's party + result for a given election (party history)."""

    __tablename__ = "party_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    politician_name: Mapped[str] = mapped_column(String(200), index=True)
    party: Mapped[str] = mapped_column(String(30), default="")
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    year: Mapped[str] = mapped_column(String(10), default="")
    election_type: Mapped[str] = mapped_column(String(30), default="")
    votes: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    running_mate: Mapped[str] = mapped_column(String(200), default="")
    constituency: Mapped[str] = mapped_column(String(80), default="")  # e.g. senate district


class Governor(Base):
    """Current (incumbent) state governor."""

    __tablename__ = "governors"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    party: Mapped[str] = mapped_column(String(30), default="")
    party_elected: Mapped[str] = mapped_column(String(30), default="")  # if defected since
    term_start: Mapped[str] = mapped_column(String(10), default="")
    term_end: Mapped[str] = mapped_column(String(10), default="")
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GovernorHistory(Base):
    """A past or present governor of a state (2007 onward)."""

    __tablename__ = "governor_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    party: Mapped[str] = mapped_column(String(30), default="")
    term_start: Mapped[str] = mapped_column(String(10), default="")
    term_end: Mapped[str] = mapped_column(String(10), default="")
    acting: Mapped[bool] = mapped_column(Boolean, default=False)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # chronological order within state
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LgaResult(Base):
    """Verified 2023 presidential result aggregated per LGA."""

    __tablename__ = "lga_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120))
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    leading_party: Mapped[str] = mapped_column(String(20), default="")
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON per-party shares
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    year: Mapped[str] = mapped_column(String(10), default="2023")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PollingUnit(Base):
    """A polling unit, with 2023 registered voters and known (cast) votes."""

    __tablename__ = "polling_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120))
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ward: Mapped[str] = mapped_column(String(160))
    ward_code: Mapped[str] = mapped_column(String(30), index=True)
    pu_name: Mapped[str] = mapped_column(String(300), default="")
    pu_code: Mapped[str] = mapped_column(String(40), default="")
    registered_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    known_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes_apc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes_lp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes_pdp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes_nnpp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner: Mapped[str] = mapped_column(String(20), default="")  # 2023 presidential winner at this PU
    runner_up: Mapped[str] = mapped_column(String(20), default="")


class WardResult(Base):
    """Aggregated 2023 presidential result per ward (from verified polling units)."""

    __tablename__ = "ward_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120))
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ward: Mapped[str] = mapped_column(String(160))
    ward_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    votes_apc: Mapped[int] = mapped_column(Integer, default=0)
    votes_lp: Mapped[int] = mapped_column(Integer, default=0)
    votes_pdp: Mapped[int] = mapped_column(Integer, default=0)
    votes_nnpp: Mapped[int] = mapped_column(Integer, default=0)
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    winner: Mapped[str] = mapped_column(String(20), default="")
    runner_up: Mapped[str] = mapped_column(String(20), default="")


class Senator(Base):
    """A member of the Senate (10th National Assembly, 2023-2027)."""

    __tablename__ = "senators"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    district: Mapped[str] = mapped_column(String(60))  # senatorial district (e.g. "Central")
    party: Mapped[str] = mapped_column(String(20), default="")
    gender: Mapped[str] = mapped_column(String(12), default="")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leadership: Mapped[str] = mapped_column(String(60), default="")  # e.g. "Senate President"
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class StatePresidential(Base):
    """2023 presidential result for a state (official, by-state)."""

    __tablename__ = "state_presidential"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    year: Mapped[int] = mapped_column(Integer, default=2023)
    apc: Mapped[int] = mapped_column(Integer, default=0)
    pdp: Mapped[int] = mapped_column(Integer, default=0)
    lp: Mapped[int] = mapped_column(Integer, default=0)
    nnpp: Mapped[int] = mapped_column(Integer, default=0)
    others: Mapped[int] = mapped_column(Integer, default=0)
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    turnout: Mapped[float | None] = mapped_column(Float, nullable=True)
    winner: Mapped[str] = mapped_column(String(20), default="")


class HouseMember(Base):
    """A member of the House of Representatives (10th Assembly, 2023-2027)."""

    __tablename__ = "house_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    constituency: Mapped[str] = mapped_column(String(160))  # federal constituency
    name: Mapped[str] = mapped_column(String(200))
    party: Mapped[str] = mapped_column(String(20), default="")
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # link if already a politician


class Ward(Base):
    """An electoral ward with its coordinates."""

    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120), index=True)
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ward: Mapped[str] = mapped_column(String(160))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class Lga(Base):
    """Canonical Local Government Area. Other records reference LGAs by this id so a
    rename here propagates everywhere (names are never stored on referencing rows)."""

    __tablename__ = "lga"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    geo_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))


class Politician(Base):
    """A political heavyweight associated with a state."""

    __tablename__ = "politicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    party: Mapped[str] = mapped_column(String(20), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    photo: Mapped[str] = mapped_column(Text, default="")  # approved official photo (data URL)
    aka: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of alternative names
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PoliticianPhoto(Base):
    """A user-submitted photo for a politician, pending admin approval."""

    __tablename__ = "politician_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    politician_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_name: Mapped[str] = mapped_column(String(200), default="")
    image: Mapped[str] = mapped_column(Text, default="")  # data URL
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PoliticianAssessment(Base):
    """A contributor's estimate of a politician's electoral value & LGA influence."""

    __tablename__ = "politician_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    politician_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_name: Mapped[str] = mapped_column(String(200), default="")
    electoral_value: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    influential_lgas: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of LGA ids (see Lga)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProblemUnit(Base):
    """A polling unit flagged for strong anomalies in the 2023 election."""

    __tablename__ = "problem_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120), default="")
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
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


class DeclaredCandidate(Base):
    """A politician publicly declared/expected to run for a party in a future
    election that hasn't happened yet -- no votes/position/percent, since
    those only make sense for a completed race (see PartyHistory for that).
    `state` is "Nigeria" for a national presidential candidacy."""

    __tablename__ = "declared_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    election_type: Mapped[str] = mapped_column(String(30), index=True)  # presidential | governor | senate
    year: Mapped[str] = mapped_column(String(10), default="2027", index=True)
    party: Mapped[str] = mapped_column(String(20), default="")
    politician_name: Mapped[str] = mapped_column(String(200))
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    running_mate: Mapped[str] = mapped_column(String(200), default="")
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
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120), default="")
    senatorial_district: Mapped[str] = mapped_column(String(120), default="")
    leading_party: Mapped[str] = mapped_column(String(20), default="")  # party with the highest score
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON: {"APC": 40, "PDP": 30, ...}
    notes: Mapped[str] = mapped_column(Text, default="")
    measurement_week: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LgaPrediction(Base):
    """A single per-LGA vote prediction: a party (and candidate) is projected to get
    `votes` votes in one local government. States/candidates are aggregated up from
    these for the /2027/<race>/states view."""

    __tablename__ = "lga_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    election_type: Mapped[str] = mapped_column(String(30), default="presidential", index=True)
    year: Mapped[str] = mapped_column(String(10), default="2027", index=True)
    party: Mapped[str] = mapped_column(String(20), default="")
    lga_id: Mapped[int] = mapped_column(Integer, index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
