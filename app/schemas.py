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
