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
import re  # noqa: E402

# Phone policy (Week 2):
# - Allowed formatting characters are spaces, dashes, dots and parentheses; they are stripped.
# - At most one '+', and only as the very first character.
# - After stripping, 7 to 15 digits are required (15 is the E.164 maximum).
# - Stored canonical form: optional leading '+' followed by digits only, e.g. "+923000000001".
# - Duplicate policy: two contacts of the same user may not share a canonical phone
#   (enforced in profiles.py with a 409). Different users may list the same number.
PHONE_ALLOWED = re.compile(r"^\+?[0-9 ().-]+$")
PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15


def normalize_phone(v: str) -> str:
    """Return the canonical phone form or raise ValueError."""
    v = v.strip()
    if not PHONE_ALLOWED.fullmatch(v):
        raise ValueError("phone may contain digits, spaces, dashes, dots, parentheses "
                         "and one leading '+' only")
    plus = v.startswith("+")
    digits = re.sub(r"\D", "", v)
    if not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS:
        raise ValueError(f"phone must contain {PHONE_MIN_DIGITS} to {PHONE_MAX_DIGITS} digits")
    return ("+" if plus else "") + digits


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
    # str_strip_whitespace runs before min_length, so "   " fails as empty.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(max_length=30)
    relationship: str = Field(min_length=1, max_length=40)

    @field_validator("phone")
    @classmethod
    def canonical_phone(cls, v: str) -> str:
        return normalize_phone(v)


class EmergencyContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    phone: str
    relationship: str


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
