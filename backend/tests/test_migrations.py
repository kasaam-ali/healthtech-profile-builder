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


def test_populated_week1_db_upgrades_and_keeps_users_and_sessions(tmp_path):
    """Week 1 data (users + admin_sessions) survives the Week 2 migration."""
    from sqlalchemy import text

    db = tmp_path / "week1.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "ENVIRONMENT": "development"}

    def alembic(*args):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    alembic("upgrade", "0001_week1_baseline")
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.execute(text("INSERT INTO users (id, email, full_name, password_hash, is_admin, created_at)"
                       " VALUES (1, 'admin@example.com', 'Admin Demo', 'x-hash', 1, '2026-01-01'),"
                       " (2, 'ayesha.demo@example.com', 'Ayesha Demo', 'y-hash', 0, '2026-01-02')"))
        c.execute(text("INSERT INTO admin_sessions (id, user_id, created_at, expires_at, revoked)"
                       " VALUES ('sess-demo-1', 1, '2026-01-01', '2099-01-01', 0)"))
    eng.dispose()
    alembic("upgrade", "head")
    with eng.connect() as c:
        users = c.execute(text("SELECT id, email, full_name, password_hash FROM users ORDER BY id")).all()
        sess = c.execute(text("SELECT id, user_id, revoked FROM admin_sessions")).all()
        # New Week 2 tables accept rows tied to the pre-existing user.
        assert c.execute(text("SELECT count(*) FROM emergency_contacts")).scalar() == 0
    assert [tuple(u) for u in users] == [(1, "admin@example.com", "Admin Demo", "x-hash"),
                                         (2, "ayesha.demo@example.com", "Ayesha Demo", "y-hash")]
    assert [tuple(s) for s in sess] == [("sess-demo-1", 1, 0)]
    with eng.begin() as c:
        c.execute(text("INSERT INTO emergency_contacts (user_id, name, phone, relationship, created_at)"
                       " VALUES (2, 'Zara Demo', '+923000000001', 'sister', '2026-01-03')"))
