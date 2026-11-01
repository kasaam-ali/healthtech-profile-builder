from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

BCRYPT_MAX_BYTES = 72


def check_password_bytes(v: str) -> str:
    """bcrypt only uses the first 72 UTF-8 bytes; reject longer instead of truncating."""
    if len(v.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes when UTF-8 encoded")
    return v


class SignupIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8)

    _pw_bytes = field_validator("password")(check_password_bytes)


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    _pw_bytes = field_validator("password")(check_password_bytes)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str


# ---------- Week 2: profile sections ----------
from datetime import date as _date  # noqa: E402
from datetime import datetime as _datetime  # noqa: E402
from typing import Literal  # noqa: E402

PHONE_PATTERN = r"^\+?[0-9 ()-]{7,20}$"


class DemographicIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_of_birth: _date | None = None
    gender: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)

    @field_validator("date_of_birth")
    @classmethod
    def dob_in_past(cls, v):
        if v is not None and (v >= _date.today() or v.year < 1900):
            raise ValueError("date_of_birth must be in the past and after 1900")
        return v


class DemographicOut(DemographicIn):
    model_config = ConfigDict(from_attributes=True)
    updated_at: _datetime


class WellnessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_level: Literal["low", "moderate", "high"]
    diet_notes: str | None = Field(default=None, max_length=500)
    reminder_opt_in: bool = False


class WellnessOut(WellnessIn):
    model_config = ConfigDict(from_attributes=True)
    updated_at: _datetime


class EmergencyContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(pattern=PHONE_PATTERN)
    relationship: str = Field(min_length=1, max_length=40)


class EmergencyContactOut(EmergencyContactIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AdminProfileRow(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    city: str | None
    country: str | None
    activity_level: str | None
    emergency_contact_count: int


class AdminProfilePage(BaseModel):
    items: list[AdminProfileRow]
    total: int
    page: int
    page_size: int
