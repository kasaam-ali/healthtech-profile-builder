from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All config comes from environment / .env (see .env.example)."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = "dev-only-insecure-jwt-secret"
    session_secret: str = "dev-only-insecure-session-secret"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    database_url: str = "sqlite:///./healthtech.db"
    cors_origins: str = "http://localhost:3000"


settings = Settings()
