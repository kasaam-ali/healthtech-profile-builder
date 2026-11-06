"""Seed FICTIONAL demo users and profile sections (no real patient data).

Run `alembic upgrade head` first. Usage: python -m scripts.seed_users
"""
from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Demographic, EmergencyContact, User, WellnessPreference
from app.security import hash_password

DEMO_PASSWORD = "DemoPass123!"  # fictional, documented in README
DEMO_USERS = [
    {"email": "ayesha.demo@example.com", "name": "Ayesha Demo",
     "demo": {"date_of_birth": date(1995, 4, 12), "gender": "female", "city": "Lahore",
              "country": "Pakistan"},
     "wellness": {"activity_level": "moderate", "diet_notes": "Fictional: prefers vegetarian",
                  "reminder_opt_in": True},
     "contacts": [{"name": "Zara Demo", "phone": "+92 300 0000001", "relationship": "sister"}]},
    {"email": "bilal.demo@example.com", "name": "Bilal Demo",
     "demo": {"date_of_birth": date(1990, 9, 3), "gender": "male", "city": "Karachi",
              "country": "Pakistan"},
     "wellness": {"activity_level": "high", "diet_notes": None, "reminder_opt_in": False},
     "contacts": [{"name": "Omar Demo", "phone": "+92 300 0000002", "relationship": "friend"}]},
]


def main():
    with SessionLocal() as db:
        for spec in DEMO_USERS:
            user = db.scalar(select(User).where(User.email == spec["email"]))
            if user is None:
                user = User(email=spec["email"], full_name=spec["name"],
                            password_hash=hash_password(DEMO_PASSWORD))
                db.add(user)
                db.flush()
            if not db.scalar(select(Demographic).where(Demographic.user_id == user.id)):
                db.add(Demographic(user_id=user.id, **spec["demo"]))
            if not db.scalar(select(WellnessPreference)
                             .where(WellnessPreference.user_id == user.id)):
                db.add(WellnessPreference(user_id=user.id, **spec["wellness"]))
            if not db.scalar(select(EmergencyContact).where(EmergencyContact.user_id == user.id)):
                for c in spec["contacts"]:
                    db.add(EmergencyContact(user_id=user.id, **c))
        db.commit()
    print("Seeded fictional users + profiles:", ", ".join(s["email"] for s in DEMO_USERS))


if __name__ == "__main__":
    main()
