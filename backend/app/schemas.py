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
