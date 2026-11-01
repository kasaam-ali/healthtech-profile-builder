"""Week 2: relational profile sections, IDOR protection, admin search, audit trail."""
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent

ORIGIN = {"Origin": "http://localhost:3000"}
PW = "DemoPass123!"


def member(client, email, name):
    assert client.post("/auth/signup", json={"email": email, "full_name": name,
                                             "password": PW}).status_code == 201
    tok = client.post("/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def admin_login(client):
    r = client.post("/admin/login", json={"email": "admin@example.com",
                                          "password": "AdminPass123!"}, headers=ORIGIN)
    assert r.status_code == 200


DEMO = {"date_of_birth": "1995-04-12", "gender": "female", "city": "Lahore", "country": "Pakistan"}
WELL = {"activity_level": "moderate", "diet_notes": "fictional note", "reminder_opt_in": True}
CONTACT = {"name": "Zara Demo", "phone": "+92 300 0000001", "relationship": "sister"}


def test_profile_routes_require_jwt(client):
    for path in ("/me/demographic", "/me/wellness", "/me/emergency-contacts"):
        assert client.get(path).status_code == 401
    assert client.put("/me/demographic", json=DEMO).status_code == 401


def test_happy_path_crud(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    assert client.get("/me/demographic", headers=a).status_code == 404
    r = client.put("/me/demographic", json=DEMO, headers=a)
    assert r.status_code == 200 and r.json()["city"] == "Lahore"
    r = client.put("/me/demographic", json={**DEMO, "city": "Karachi"}, headers=a)
    assert client.get("/me/demographic", headers=a).json()["city"] == "Karachi"

    assert client.put("/me/wellness", json=WELL, headers=a).status_code == 200
    assert client.get("/me/wellness", headers=a).json()["activity_level"] == "moderate"

    c = client.post("/me/emergency-contacts", json=CONTACT, headers=a)
    assert c.status_code == 201
    cid = c.json()["id"]
    r = client.put(f"/me/emergency-contacts/{cid}", json={**CONTACT, "relationship": "friend"},
                   headers=a)
    assert r.json()["relationship"] == "friend"
    assert len(client.get("/me/emergency-contacts", headers=a).json()) == 1
    assert client.delete(f"/me/emergency-contacts/{cid}", headers=a).status_code == 204
    assert client.get("/me/emergency-contacts", headers=a).json() == []
    assert client.delete("/me/wellness", headers=a).status_code == 204
    assert client.delete("/me/demographic", headers=a).status_code == 204
    assert client.get("/me/demographic", headers=a).status_code == 404


def test_idor_user_a_cannot_touch_user_b(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    b = member(client, "bilal.demo@example.com", "Bilal Demo")
    client.put("/me/demographic", json=DEMO, headers=b)
    cid = client.post("/me/emergency-contacts", json=CONTACT, headers=b).json()["id"]

    # A cannot read, edit, or delete B's contact by id.
    assert client.get(f"/me/emergency-contacts/{cid}", headers=a).status_code == 404
    assert client.put(f"/me/emergency-contacts/{cid}", json={**CONTACT, "name": "Hacked"},
                      headers=a).status_code == 404
    assert client.delete(f"/me/emergency-contacts/{cid}", headers=a).status_code == 404
    assert client.get("/me/emergency-contacts", headers=a).json() == []
    # A's /me/demographic is A's own (empty), never B's.
    assert client.get("/me/demographic", headers=a).status_code == 404
    # Client-supplied user_id is rejected, not trusted.
    assert client.put("/me/demographic", json={**DEMO, "user_id": 2},
                      headers=a).status_code == 422
    # B's data is untouched.
    assert client.get(f"/me/emergency-contacts/{cid}", headers=b).json()["name"] == "Zara Demo"
    assert client.get("/me/demographic", headers=b).json()["city"] == "Lahore"


def test_malformed_input_422(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    assert client.put("/me/demographic", json={"date_of_birth": "not-a-date"},
                      headers=a).status_code == 422
    assert client.put("/me/demographic", json={"date_of_birth": "2999-01-01"},
                      headers=a).status_code == 422
    assert client.put("/me/wellness", json={"activity_level": "extreme"},
                      headers=a).status_code == 422
    assert client.post("/me/emergency-contacts", json={**CONTACT, "phone": "call me"},
                       headers=a).status_code == 422
    assert client.post("/me/emergency-contacts", json={"name": ""},
                       headers=a).status_code == 422
    assert client.get("/me/emergency-contacts/abc", headers=a).status_code == 422


def test_emergency_contact_limit(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    for _ in range(5):
        assert client.post("/me/emergency-contacts", json=CONTACT, headers=a).status_code == 201
    assert client.post("/me/emergency-contacts", json=CONTACT, headers=a).status_code == 409


def test_admin_search_requires_admin_session_not_jwt(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    assert client.get("/admin/profiles").status_code == 403
    assert client.get("/admin/profiles", headers=a).status_code == 403
    # Admin session does not grant access to member JWT routes.
    admin_login(client)
    assert client.get("/me/demographic").status_code == 401


def test_admin_search_pagination_and_filters(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    b = member(client, "bilal.demo@example.com", "Bilal Demo")
    member(client, "chand.demo@example.com", "Chand Demo")
    client.put("/me/demographic", json=DEMO, headers=a)
    client.put("/me/demographic", json={**DEMO, "city": "Karachi"}, headers=b)
    admin_login(client)

    r = client.get("/admin/profiles", params={"page_size": 2})
    body = r.json()
    assert r.status_code == 200 and body["total"] == 3 and len(body["items"]) == 2
    assert all(i["email"] != "admin@example.com" for i in body["items"])
    page2 = client.get("/admin/profiles", params={"page_size": 2, "page": 2}).json()
    assert len(page2["items"]) == 1

    r = client.get("/admin/profiles", params={"city": "Karachi"}).json()
    assert [i["email"] for i in r["items"]] == ["bilal.demo@example.com"]
    r = client.get("/admin/profiles", params={"q": "AYESHA"}).json()
    assert r["total"] == 1 and r["items"][0]["city"] == "Lahore"
    assert client.get("/admin/profiles", params={"page": 0}).status_code == 422
    assert client.get("/admin/profiles", params={"page_size": 1000}).status_code == 422


def test_audit_rows_written_without_secrets(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    client.put("/me/demographic", json=DEMO, headers=a)
    client.put("/me/demographic", json={**DEMO, "city": "Karachi"}, headers=a)
    admin_login(client)
    client.get("/admin/profiles", params={"q": "ayesha"})
    with SessionLocal() as db:
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    actions = [(e.action, e.resource_type) for e in events]
    assert ("profile.create", "demographic") in actions
    assert ("profile.update", "demographic") in actions
    assert ("admin.profiles.list", "profile") in actions
    upd = next(e for e in events if e.action == "profile.update")
    assert upd.metadata_json == {"fields": ["city"]} and upd.created_at is not None
    dump = repr([(e.metadata_json, e.resource_id) for e in events])
    for bad in ("Karachi", "Lahore", "ayesha", "Bearer", PW, "password"):
        assert bad not in dump
