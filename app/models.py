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
    """ARCHIVED legacy table (renamed to lga_results_archive by migration 0046). No live
    app code reads this — results now live in the unified LgaResultV tables. Kept only so
    the local `pick_definitive_results.py --from-archive` script can import the old data."""

    __tablename__ = "lga_results_archive"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(50), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120))
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    leading_party: Mapped[str] = mapped_column(String(20), default="")
    scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON per-party shares
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    year: Mapped[str] = mapped_column(String(10), default="2023")


class LgaPartyResult(Base):
    """ARCHIVED legacy table (renamed to lga_party_results_archive by migration 0046). No
    live app code reads this — LGA results now live in the unified LgaResultV tables. Kept
    only for the local `pick_definitive_results.py --from-archive` import."""

    __tablename__ = "lga_party_results_archive"

    id: Mapped[int] = mapped_column(primary_key=True)
    election_type: Mapped[str] = mapped_column(String(20), index=True)  # presidential | governor
    year: Mapped[str] = mapped_column(String(10), default="2023", index=True)
    state: Mapped[str] = mapped_column(String(60), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120))
    party: Mapped[str] = mapped_column(String(20), index=True)
    votes: Mapped[int] = mapped_column(Integer, default=0)


class LegislativeResult(Base):
    """One candidate's result in one National Assembly race — tidy long form (one
    row per election_type/year/constituency/candidate). Holds the verified 2019
    Senate + House of Representatives results parsed from the INEC constituency
    result sheets. Candidates are linked to a politician_id where one matches."""

    __tablename__ = "legislative_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    election_type: Mapped[str] = mapped_column(String(20), index=True)  # senate | house
    year: Mapped[str] = mapped_column(String(10), default="2019", index=True)
    state: Mapped[str] = mapped_column(String(60), index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    constituency: Mapped[str] = mapped_column(String(160), index=True)  # federal constituency / senatorial district
    code: Mapped[str] = mapped_column(String(20), default="")  # INEC code e.g. FC/003/AB, SD/002/AB
    candidate: Mapped[str] = mapped_column(String(200), default="")
    gender: Mapped[str] = mapped_column(String(2), default="")
    party: Mapped[str] = mapped_column(String(20), index=True, default="")
    votes: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)  # rank within constituency, 1 = top
    elected: Mapped[bool] = mapped_column(Boolean, default=False)
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class ElectionSheet(Base):
    """Link from a polling unit to its INEC IReV result sheet and our transcription.
    One row per (pu_code, election_type, year). `sheet_url` points at INEC's own server
    (we do not re-host the scan); `sheet_status` is our download outcome; `json` holds the
    verbatim EC8A transcription (JSON text) where we have produced one. Joined to a
    polling unit by matching pu_code (same INEC state/lga/ward/pu code)."""

    __tablename__ = "election_sheets"

    id: Mapped[int] = mapped_column(primary_key=True)
    election_type: Mapped[str] = mapped_column(String(20), index=True)  # presidential|governorship|senatorial
    year: Mapped[str] = mapped_column(String(10), default="2023", index=True)
    state: Mapped[str] = mapped_column(String(60), default="")
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    pu_code: Mapped[str] = mapped_column(String(40), index=True)  # INEC code, e.g. 03/01/01/001
    sheet_url: Mapped[str] = mapped_column(Text, default="")      # INEC IReV sheet (their server)
    sheet_status: Mapped[str] = mapped_column(String(20), default="")  # saved | no_sheet | dead
    json: Mapped[str | None] = mapped_column(Text, nullable=True)  # our EC8A transcription, JSON text


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
    """ARCHIVED legacy table (renamed to ward_results_archive by migration 0046). No live
    app code reads this — ward results now live in the unified WardResultV tables. Kept
    only for the local `pick_definitive_results.py --from-archive` import."""

    __tablename__ = "ward_results_archive"

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
    """ARCHIVED legacy table (renamed to state_presidential_archive by migration 0046). No
    live app code reads this — state results now live in the unified StateResultV tables.
    Kept only for the local `pick_definitive_results.py --from-archive` import."""

    __tablename__ = "state_presidential_archive"

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
    # Current party — derived from the newest electoral history (their latest run or
    # declared candidacy) and kept in sync by refresh_politician_parties(). Not edited
    # directly; a defection shows up as a new PartyHistory/DeclaredCandidate entry.
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


class WardPrediction(Base):
    """A per-ward vote projection for one candidate in one race. A candidate may have
    several predictions for the same ward (different bases/scenarios), told apart by
    `label`. LGA- and state-level figures are aggregated up from these rows."""

    __tablename__ = "ward_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    election_type: Mapped[str] = mapped_column(String(30), default="presidential", index=True)
    year: Mapped[str] = mapped_column(String(10), default="2027", index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga_id: Mapped[int] = mapped_column(Integer, index=True)
    ward_code: Mapped[str] = mapped_column(String(30), default="", index=True)
    # a prediction is for a joint ticket: the presidential candidate (politician_id) and
    # his running mate / VP (running_mate_id). Grouped and displayed as "Obi/Kwankwaso".
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    running_mate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    party: Mapped[str] = mapped_column(String(20), default="")
    votes: Mapped[int] = mapped_column(Integer, default=0)  # sum of this prediction's components
    label: Mapped[str] = mapped_column(String(80), default="")  # basis of the prediction
    importance: Mapped[int] = mapped_column(Integer, default=50)  # weight (0-100) in the average
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionComponent(Base):
    """One building block of a ward prediction: a reason and the votes it contributes
    (e.g. Candidate Popularity = 70k). A prediction's votes is the sum of its
    components."""

    __tablename__ = "prediction_components"

    id: Mapped[int] = mapped_column(primary_key=True)
    ward_prediction_id: Mapped[int] = mapped_column(Integer, index=True)
    reason: Mapped[str] = mapped_column(String(80), default="")
    votes: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    # the politician this component's support is drawn from, when any: the presidential
    # candidate for "Candidate Popularity", the running mate for "Running-mate Popularity"
    # (matched against the votes that VP delivered in a past election), None for party base.
    politician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ===========================================================================
# Unified election-results architecture
# ===========================================================================
# One normalized spine from the scanned INEC sheet down to (or up from) any geo
# level. Votes are ALWAYS long-form — one row per party in a `*_result_party`
# child table — so the model is party-agnostic (full ballot, any office via
# `election_type`) and every level shares the same shape and serializer.
#
#   election_sheet ──< evidence ──< evidence_party                   (pieces of evidence)
#   pu_result ──< pu_result_party                                    (derived definitive PU)
#   ward_result / lga_result / state_result  (+ *_party)             (per-level result)
#
# EVIDENCE: every recorded number for a unit is a piece of evidence. The INEC-reported
# figure is the FIRST piece of evidence (kind='inec'); LLM- and human-transcribed sheets
# are further evidence. pu_result is DERIVED from weighing the evidence and points at the
# chosen row. So any unit with a result always has >=1 evidence row.
#
# CRITICAL: the ward/lga/state result tables are FIRST-CLASS and directly
# writable — not caches derived only from pu_result. Data often arrives top-down
# (2019 presidential is state-only; 2023 governorship is LGA-only). Each result
# row records how it was populated via `source`:
#   declared  — hand-loaded / entered directly (no finer data required)
#   rolled_up — computed by the definitive-picker script from finer levels
#   official  — an INEC-published figure
# The picker only fills/refreshes levels it can compute; it never erases a
# coarser declared/official result because finer data is missing.

# Recognised values for the `source` column on every *_result table.
RESULT_SOURCES = ("declared", "rolled_up", "official")
# Recognised election types (offices).
ELECTION_TYPES = ("presidential", "governor", "senate", "house")


# Recognised kinds of evidence (the type of a recorded figure). Every piece is a GUESS —
# there is no "definitive" and no single "chosen" evidence; the unit result is a MERGE.
EVIDENCE_KINDS = ("2023_transcription", "inec", "llm", "human", "crowd")


class Evidence(Base):
    """One PIECE OF EVIDENCE for a polling unit's result in one election. Every recorded
    number is evidence: the INEC-reported figure (kind='inec'), an LLM transcription of the
    scanned sheet (kind='llm'), a human transcription (kind='human'), etc. Party votes live
    in the child `evidence_party` rows; the poll-summary fields are captured here.

    Provenance (so multiple evidence points are distinguishable and weightable):
      kind           — the type of evidence (inec | llm | human | crowd)
      source         — where it came from: 'INEC IReV', an LLM model name, a sheet id/url…
      submitted_by   — human-readable label of who added it
      submitted_by_id— the users.id who added it (for weighting), when known
    `raw` keeps the verbatim original payload for audit."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    sheet_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # FK election_sheets.id
    pu_code: Mapped[str] = mapped_column(String(40), index=True)  # denormalized for direct lookup
    election_type: Mapped[str] = mapped_column(String(20), index=True, default="presidential")
    year: Mapped[str] = mapped_column(String(10), default="2023", index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True, default="inec")  # see EVIDENCE_KINDS
    source: Mapped[str] = mapped_column(String(120), index=True, default="")   # where it came from
    method: Mapped[str] = mapped_column(String(60), default="")   # free text describing how
    submitted_by: Mapped[str] = mapped_column(String(120), index=True, default="")  # who added it (label)
    submitted_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # users.id
    # poll summary (all nullable — a piece of evidence may omit some fields)
    registered_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accredited_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_used_ballots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)  # verbatim original JSON, audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceParty(Base):
    """One party's recorded votes within a single piece of evidence (long form)."""

    __tablename__ = "evidence_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(Integer, index=True)  # FK evidence.id
    party: Mapped[str] = mapped_column(String(20), index=True)
    votes: Mapped[int | None] = mapped_column(Integer, nullable=True)   # figure (may be blank on sheet)
    votes_words: Mapped[str] = mapped_column(String(120), default="")   # votes in words, verbatim


class PuResult(Base):
    """The MERGED result for one polling unit in one election — combined from the evidence
    (today: a copy of the single entry; a real merge routine can recompute it later). There
    is NO single "chosen" evidence and NO "definitive": every piece of evidence is a guess.
    `method` records how it was merged. Party-by-party votes are in `pu_result_party` when
    known. Accredited voters live on the evidence entry, not here (entries can differ)."""

    __tablename__ = "pu_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    pu_code: Mapped[str] = mapped_column(String(40), index=True)
    election_type: Mapped[str] = mapped_column(String(20), index=True, default="presidential")
    year: Mapped[str] = mapped_column(String(10), default="2023", index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ward_code: Mapped[str] = mapped_column(String(30), default="", index=True)
    winner: Mapped[str] = mapped_column(String(20), default="")
    runner_up: Mapped[str] = mapped_column(String(20), default="")
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    valid_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="declared")  # see RESULT_SOURCES
    method: Mapped[str] = mapped_column(String(60), default="")  # how the result was merged
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PuResultParty(Base):
    """One party's votes in a polling unit's definitive result (long form)."""

    __tablename__ = "pu_result_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    pu_result_id: Mapped[int] = mapped_column(Integer, index=True)  # FK pu_results.id
    party: Mapped[str] = mapped_column(String(20), index=True)
    votes: Mapped[int] = mapped_column(Integer, default=0)


class WardResultV(Base):
    """A ward's result in one election (directly writable OR rolled up from PUs).
    Same shape as PuResult without pu_code. Party votes in `ward_result_parties`."""

    __tablename__ = "ward_result_v"

    id: Mapped[int] = mapped_column(primary_key=True)
    ward_code: Mapped[str] = mapped_column(String(30), index=True)
    election_type: Mapped[str] = mapped_column(String(20), index=True, default="presidential")
    year: Mapped[str] = mapped_column(String(10), default="2023", index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ward: Mapped[str] = mapped_column(String(160), default="")
    winner: Mapped[str] = mapped_column(String(20), default="")
    runner_up: Mapped[str] = mapped_column(String(20), default="")
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    valid_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="declared")  # see RESULT_SOURCES
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WardResultParty(Base):
    __tablename__ = "ward_result_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    ward_result_id: Mapped[int] = mapped_column(Integer, index=True)  # FK ward_result_v.id
    party: Mapped[str] = mapped_column(String(20), index=True)
    votes: Mapped[int] = mapped_column(Integer, default=0)


class LgaResultV(Base):
    """An LGA's result in one election (directly writable OR rolled up). Party votes
    in `lga_result_parties`."""

    __tablename__ = "lga_result_v"

    id: Mapped[int] = mapped_column(primary_key=True)
    lga_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    lga: Mapped[str] = mapped_column(String(120), default="")
    election_type: Mapped[str] = mapped_column(String(20), index=True, default="presidential")
    year: Mapped[str] = mapped_column(String(10), default="2023", index=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    winner: Mapped[str] = mapped_column(String(20), default="")
    runner_up: Mapped[str] = mapped_column(String(20), default="")
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    valid_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="declared")  # see RESULT_SOURCES
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LgaResultParty(Base):
    __tablename__ = "lga_result_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    lga_result_id: Mapped[int] = mapped_column(Integer, index=True)  # FK lga_result_v.id
    party: Mapped[str] = mapped_column(String(20), index=True)
    votes: Mapped[int] = mapped_column(Integer, default=0)


class StateResultV(Base):
    """A state's result in one election (directly writable OR rolled up). Party votes
    in `state_result_parties`. This is where state-only data (e.g. 2019 presidential)
    lives natively."""

    __tablename__ = "state_result_v"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_geo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(60), default="")
    election_type: Mapped[str] = mapped_column(String(20), index=True, default="presidential")
    year: Mapped[str] = mapped_column(String(10), default="2023", index=True)
    winner: Mapped[str] = mapped_column(String(20), default="")
    runner_up: Mapped[str] = mapped_column(String(20), default="")
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    valid_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="declared")  # see RESULT_SOURCES
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StateResultParty(Base):
    __tablename__ = "state_result_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_result_id: Mapped[int] = mapped_column(Integer, index=True)  # FK state_result_v.id
    party: Mapped[str] = mapped_column(String(20), index=True)
    votes: Mapped[int] = mapped_column(Integer, default=0)
