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
