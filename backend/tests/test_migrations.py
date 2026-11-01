"""Alembic: upgrade head on a clean SQLite DB produces the same schema as the models."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_head_on_clean_db(tmp_path):
    db = tmp_path / "mig.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "ENVIRONMENT": "development"}
    for args in (["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    insp = inspect(create_engine(f"sqlite:///{db}"))
    tables = set(insp.get_table_names())
    assert {"users", "admin_sessions", "demographics", "wellness_preferences",
            "emergency_contacts", "audit_events", "alembic_version"} <= tables
    idx = {i["name"] for t in tables for i in insp.get_indexes(t)}
    assert {"ix_demographics_user_id", "ix_demographics_city", "ix_audit_actor_created",
            "ix_emergency_contacts_user_id", "ix_users_email"} <= idx
