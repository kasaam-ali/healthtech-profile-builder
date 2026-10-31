"""Seed FICTIONAL demo users only (no real patient data). Usage: python -m scripts.seed_users"""
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password

DEMO_USERS = [
    ("ayesha.demo@example.com", "Ayesha Demo"),
    ("bilal.demo@example.com", "Bilal Demo"),
]
DEMO_PASSWORD = "DemoPass123!"  # fictional, documented in README


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for email, name in DEMO_USERS:
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, full_name=name, password_hash=hash_password(DEMO_PASSWORD)))
        db.commit()
    print("Seeded fictional users:", ", ".join(e for e, _ in DEMO_USERS))


if __name__ == "__main__":
    main()
