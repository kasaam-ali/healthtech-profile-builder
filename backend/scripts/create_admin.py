"""Create or reset the admin account. No public admin signup exists.

Usage (from backend/, after `alembic upgrade head`):  python -m scripts.create_admin
Reads ADMIN_EMAIL / ADMIN_PASSWORD from the environment or .env.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security import hash_password


class AdminEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    admin_email: str
    admin_password: str


def main():
    env = AdminEnv()
    # Schema comes from Alembic: run `alembic upgrade head` first.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == env.admin_email))
        if user is None:
            user = User(email=env.admin_email, full_name="Admin (fictional)")
            db.add(user)
        user.password_hash = hash_password(env.admin_password)
        user.is_admin = True
        db.commit()
    print(f"Admin ready: {env.admin_email}")


if __name__ == "__main__":
    main()
