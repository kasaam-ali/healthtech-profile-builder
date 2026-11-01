from pydantic_settings import BaseSettings, SettingsConfigDict

# Publicly known local-only defaults. Allowed ONLY when ENVIRONMENT=development.
DEV_JWT_SECRET = "dev-only-insecure-jwt-secret"
DEV_SESSION_SECRET = "dev-only-insecure-session-secret"
KNOWN_WEAK_SECRETS = {
    DEV_JWT_SECRET, DEV_SESSION_SECRET, "",
    "change-me-to-a-long-random-string", "change-me-another-long-random-string",
    "secret", "changeme",
}
MIN_SECRET_LEN = 32


class Settings(BaseSettings):
    """All config comes from environment / .env (see .env.example)."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "production"  # fail closed: must opt in to development
    jwt_secret: str = ""
    session_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    admin_session_hours: int = 8
    database_url: str = "sqlite:///./healthtech.db"
    cors_origins: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() != "development"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


class InsecureConfigError(RuntimeError):
    pass


def finalize_settings(s: Settings) -> Settings:
    """Apply dev defaults or refuse to start in production with weak secrets."""
    env = s.environment.lower()
    if env not in {"development", "production"}:
        raise InsecureConfigError("ENVIRONMENT must be 'development' or 'production'")
    if env == "development":
        s.jwt_secret = s.jwt_secret or DEV_JWT_SECRET
        s.session_secret = s.session_secret or DEV_SESSION_SECRET
        return s
    for name in ("jwt_secret", "session_secret"):
        value = getattr(s, name)
        if value in KNOWN_WEAK_SECRETS or len(value) < MIN_SECRET_LEN:
            raise InsecureConfigError(
                f"{name.upper()} is missing, a known default, or shorter than "
                f"{MIN_SECRET_LEN} chars; refusing to start in production")
    if s.jwt_secret == s.session_secret:
        raise InsecureConfigError("JWT_SECRET and SESSION_SECRET must differ")
    return s


settings = finalize_settings(Settings())
