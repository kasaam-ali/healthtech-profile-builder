"""Tests for mentor review on PR #2 (secrets, sessions, bcrypt bytes, CSRF, role separation)."""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import (DEV_JWT_SECRET, DEV_SESSION_SECRET, InsecureConfigError, Settings,
                        finalize_settings)
from app.db import SessionLocal
from app.models import AdminSession

ORIGIN = {"Origin": "http://localhost:3000"}
ADMIN = {"email": "admin@example.com", "password": "AdminPass123!"}
STRONG_A = "a" * 20 + "Z9x!k2Lq8Rw3Tt0Pm5"
STRONG_B = "b" * 20 + "Q7v@n4Hs1Yc6Ju2Dd8"
BACKEND = Path(__file__).resolve().parents[1]


def admin_login(client, headers=ORIGIN):
    return client.post("/admin/login", json=ADMIN, headers=headers)


# ---------- P1: fail-closed secrets ----------
@pytest.mark.parametrize("jwt,sess", [("", ""), (DEV_JWT_SECRET, STRONG_B), (STRONG_A, DEV_SESSION_SECRET),
                                      ("short", STRONG_B), (STRONG_A, STRONG_A)])
def test_production_rejects_missing_weak_or_default_secrets(jwt, sess):
    with pytest.raises(InsecureConfigError):
        finalize_settings(Settings(_env_file=None, environment="production",
                                   jwt_secret=jwt, session_secret=sess))


def test_environment_defaults_to_production_and_fails_closed(monkeypatch):
    for k in ("ENVIRONMENT", "JWT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(InsecureConfigError):
        finalize_settings(Settings(_env_file=None))


def test_production_accepts_strong_secrets_and_secure_cookie():
    s = finalize_settings(Settings(_env_file=None, environment="production",
                                   jwt_secret=STRONG_A, session_secret=STRONG_B))
    assert s.is_production  # main.py passes https_only=settings.is_production


def test_development_uses_explicit_local_defaults_and_http_cookie(monkeypatch):
    for k in ("JWT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)
    s = finalize_settings(Settings(_env_file=None, environment="development"))
    assert s.jwt_secret == DEV_JWT_SECRET and not s.is_production


def _start_app(env, tmp_path):
    clean = {k: v for k, v in os.environ.items()
             if k not in {"ENVIRONMENT", "JWT_SECRET", "SESSION_SECRET"}}
    clean.update(env, DATABASE_URL="sqlite:///:memory:", PYTHONPATH=str(BACKEND))
    # cwd=tmp_path so a developer's local .env is not picked up
    return subprocess.run([sys.executable, "-c", "import app.main"], cwd=tmp_path, env=clean,
                          capture_output=True, text=True)


def test_app_startup_refuses_unconfigured_production(tmp_path):
    r = _start_app({"ENVIRONMENT": "production"}, tmp_path)
    assert r.returncode != 0 and "InsecureConfigError" in r.stderr


def test_app_startup_ok_with_strong_production_secrets(tmp_path):
    r = _start_app({"ENVIRONMENT": "production", "JWT_SECRET": STRONG_A, "SESSION_SECRET": STRONG_B},
                   tmp_path)
    assert r.returncode == 0, r.stderr


# ---------- P2: revocable server-side admin sessions ----------
def test_cookie_holds_only_opaque_id_stored_server_side(client):
    assert admin_login(client).status_code == 200
    with SessionLocal() as db:
        recs = db.query(AdminSession).all()
        assert len(recs) == 1 and not recs[0].revoked and len(recs[0].id) >= 40


def test_logout_replay_of_saved_cookie_is_rejected(client):
    assert admin_login(client).status_code == 200
    saved = client.cookies.get("session")
    assert client.get("/admin/users").status_code == 200
    assert client.post("/admin/logout", headers=ORIGIN).status_code == 200
    client.cookies.set("session", saved)  # attacker replays the pre-logout cookie
    assert client.get("/admin/users").status_code == 403


def test_login_rotates_session_id(client):
    admin_login(client)
    first = client.cookies.get("session")
    admin_login(client)
    client.cookies.set("session", first)
    assert client.get("/admin/users").status_code == 403  # old id revoked on re-login


def test_expired_session_is_rejected(client):
    admin_login(client)
    with SessionLocal() as db:
        rec = db.query(AdminSession).one()
        rec.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert client.get("/admin/users").status_code == 403


def test_tampered_cookie_is_rejected(client):
    admin_login(client)
    c = client.cookies.get("session")
    client.cookies.set("session", c[:-4] + ("AAAA" if not c.endswith("AAAA") else "BBBB"))
    assert client.get("/admin/users").status_code == 403


def test_demoted_admin_session_is_rejected(client):
    admin_login(client)
    from app.models import User
    with SessionLocal() as db:
        db.query(User).filter_by(email=ADMIN["email"]).one().is_admin = False
        db.commit()
    assert client.get("/admin/users").status_code == 403


# ---------- CSRF / trusted Origin ----------
def test_admin_login_requires_trusted_origin(client):
    assert admin_login(client, headers={}).status_code == 403
    assert admin_login(client, headers={"Origin": "https://evil.example"}).status_code == 403
    assert admin_login(client, headers={"Referer": "https://evil.example/x"}).status_code == 403
    assert admin_login(client, headers={"Referer": "http://localhost:3000/admin"}).status_code == 200


def test_admin_logout_requires_trusted_origin(client):
    admin_login(client)
    assert client.post("/admin/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/admin/users").status_code == 200  # cross-site logout did nothing
    assert client.post("/admin/logout").status_code == 403
    assert client.post("/admin/logout", headers=ORIGIN).status_code == 200


# ---------- bcrypt 72-byte UTF-8 limit ----------
def _signup(client, pw):
    return client.post("/auth/signup", json={"email": "b@example.com", "full_name": "B", "password": pw})


def test_ascii_72_bytes_ok_73_rejected(client):
    assert _signup(client, "x" * 72).status_code == 201
    r = _signup(client, "y" * 73)
    assert r.status_code == 422 and "72 bytes" in r.text


def test_multibyte_under_72_chars_over_72_bytes_rejected(client):
    pw = "é" * 37  # 37 chars, 74 bytes
    assert len(pw) <= 72 and len(pw.encode()) > 72
    r = _signup(client, pw)
    assert r.status_code == 422 and "72 bytes" in r.text
    assert _signup(client, "é" * 36).status_code == 201  # exactly 72 bytes


def test_login_also_enforces_byte_limit(client):
    _signup(client, "x" * 72)
    r = client.post("/auth/login", json={"email": "b@example.com", "password": "x" * 72 + "extra"})
    assert r.status_code == 422  # no silent truncation that would match the 72-byte prefix


# ---------- Role separation ----------
def test_admin_cannot_get_member_jwt(client):
    r = client.post("/auth/login", json=ADMIN)
    assert r.status_code == 403 and "admin/login" in r.text
