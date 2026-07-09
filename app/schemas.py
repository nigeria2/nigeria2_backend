"""Pydantic request/response schemas."""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class JoinIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    mobile: str = Field(min_length=3, max_length=40)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v


class JoinOut(BaseModel):
    id: int
    message: str = "joined"


# --- auth ---
class GoogleAuthIn(BaseModel):
    credential: str = Field(min_length=10)


class ProfileUpdate(BaseModel):
    """Partial update of the contributor profile (used by onboarding)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = None
    phone: str | None = None
    gender: str | None = None
    year_of_birth: int | None = None
    home_state: str | None = None
    home_lga: str | None = None
    residence_state: str | None = None
    voter_status: str | None = None
    known_states: list[str] | None = None
    bio: str | None = None
    onboarded: bool | None = None


class AnalysisIn(BaseModel):
    """A contributor's per-party projection for a state."""

    model_config = ConfigDict(str_strip_whitespace=True)

    election_type: str = Field(min_length=1, max_length=30)
    state: str = Field(min_length=1, max_length=50)
    lga: str | None = None
    senatorial_district: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


class PredictionSetIn(BaseModel):
    """Admin: set the official per-party prediction for a state/type/week."""

    model_config = ConfigDict(str_strip_whitespace=True)

    election_type: str = Field(min_length=1, max_length=30)
    week: str = Field(min_length=1, max_length=10)
    state: str = Field(min_length=1, max_length=50)
    scores: dict[str, float] = Field(default_factory=dict)


class PartyElectionSetIn(BaseModel):
    """Admin: set which party acronyms are relevant for an election type."""

    model_config = ConfigDict(str_strip_whitespace=True)

    election_type: str = Field(min_length=1, max_length=30)
    acronyms: list[str] = Field(default_factory=list)


class StatePredictionIn(BaseModel):
    """Create a prediction on the shared board."""

    model_config = ConfigDict(str_strip_whitespace=True)

    state: str = Field(min_length=1, max_length=50)
    election_type: str = Field(min_length=1, max_length=30)
    scores: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None
    label: str | None = None
    source: str | None = None  # admins may set 'past_performance'; otherwise 'expert'


class StatePredictionUpdate(BaseModel):
    """Edit an existing board prediction (partial)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    election_type: str | None = None
    scores: dict[str, float] | None = None
    notes: str | None = None
    label: str | None = None


class ScenarioIn(BaseModel):
    """Admin: create a prediction scenario."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    election_type: str = "presidential"


class ScenarioPoliticianIn(BaseModel):
    """Admin: attach a politician's assumed influence to a scenario."""

    model_config = ConfigDict(str_strip_whitespace=True)

    politician_id: int
    new_party: str = Field(min_length=1, max_length=20)
    delta_popularity: float = 0.0
    influence_pct: float = Field(default=0.0, ge=0, le=100)
    scope: str = "local"  # local | national | election


class DeclaredCandidateIn(BaseModel):
    """Admin: declare a politician as a party's candidate for a future election."""

    model_config = ConfigDict(str_strip_whitespace=True)

    state: str = Field(min_length=1, max_length=50)  # "Nigeria" for a national presidential run
    election_type: str = Field(min_length=1, max_length=30)  # presidential | governor | senate
    year: str = "2027"
    party: str = Field(default="", max_length=20)
    politician_name: str = Field(min_length=1, max_length=200)
    politician_id: int | None = None
    running_mate: str = ""


class ScenarioTrendIn(BaseModel):
    """Admin: add a free-form popularity trend to a scenario."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    shift_pct: float = Field(ge=0, le=100)
    target_party: str = Field(min_length=1, max_length=20)
    scope_states: list[str] = Field(default_factory=list)


class PoliticianIn(BaseModel):
    """Admin: add a politician."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=50)
    title: str | None = None
    party: str | None = None
    note: str | None = None


class PhotoSubmitIn(BaseModel):
    """Submit a photo (small data URL) for a politician."""

    image: str = Field(min_length=20, max_length=800_000)


class AssessmentIn(BaseModel):
    """Estimate a politician's electoral value and LGA influence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    electoral_value: int = Field(ge=0, le=100)
    influential_lgas: list[str] = Field(default_factory=list)
    reason: str | None = None
