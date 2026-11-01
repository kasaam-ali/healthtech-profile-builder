
ORIGIN = {"Origin": "http://localhost:3000"}
USER = {"email": "sara.demo@example.com", "full_name": "Sara Demo", "password": "DemoPass123!"}


def signup_and_login(client):
    assert client.post("/auth/signup", json=USER).status_code == 201
    r = client.post("/auth/login", json={"email": USER["email"], "password": USER["password"]})
    assert r.status_code == 200
    return r.json()


def test_unauthenticated_me_fails(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_signup_login_me(client):
    tokens = signup_and_login(client)
    r = client.get("/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == USER["email"]
    assert "password" not in r.text and "password_hash" not in r.text


def test_wrong_password_and_duplicate(client):
    signup_and_login(client)
    assert client.post("/auth/signup", json=USER).status_code == 409
    bad = client.post("/auth/login", json={"email": USER["email"], "password": "wrongpass1"})
    assert bad.status_code == 401


def test_password_is_hashed(client):
    signup_and_login(client)
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.query(User).filter_by(email=USER["email"]).one()
        assert u.password_hash != USER["password"] and u.password_hash.startswith("$2")


def test_refresh_token_cannot_be_used_as_access(client):
    tokens = signup_and_login(client)
    r = client.get("/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]


def test_signup_cannot_make_admin(client):
    body = {**USER, "is_admin": True}
    client.post("/auth/signup", json=body)
    r = client.post("/admin/login", json={"email": USER["email"], "password": USER["password"]},
                    headers=ORIGIN)
    assert r.status_code == 401


def test_user_jwt_cannot_access_admin(client):
    tokens = signup_and_login(client)
    r = client.get("/admin/users", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 403


def test_unauthenticated_admin_fails(client):
    assert client.get("/admin/users").status_code == 403


def test_admin_session_flow(client):
    r = client.post("/admin/login", json={"email": "admin@example.com", "password": "AdminPass123!"},
                    headers=ORIGIN)
    assert r.status_code == 200
    assert client.get("/admin/users").status_code == 200  # session cookie kept by client
    client.post("/admin/logout", headers=ORIGIN)
    assert client.get("/admin/users").status_code == 403
