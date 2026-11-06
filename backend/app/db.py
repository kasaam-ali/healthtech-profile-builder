from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# timeout: bounded SQLite busy wait (seconds) used by BEGIN IMMEDIATE quota reservations.

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 5})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
