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
    for i in range(5):
        r = client.post("/me/emergency-contacts", json={**CONTACT, "phone": f"+92 300 000000{i}"},
                        headers=a)
        assert r.status_code == 201
    r = client.post("/me/emergency-contacts", json={**CONTACT, "phone": "+92 300 0000009"},
                    headers=a)
    assert r.status_code == 409


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


# ---------- Mentor review fixes (PR #3) ----------
import threading  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import audit as audit_mod  # noqa: E402
from app import profiles as profiles_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Demographic, EmergencyContact  # noqa: E402


def _contact(i):
    return {"name": f"Contact {i}", "phone": f"+92 300 000000{i}", "relationship": "friend"}


def test_contact_limit_two_connection_race(client, monkeypatch):
    """From 4 contacts, request A holds its write reservation (paused before commit) while
    request B starts. B must wait, then see 5 and get the documented 409 with no audit row."""
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    for i in range(4):
        assert client.post("/me/emergency-contacts", json=_contact(i), headers=a).status_code == 201

    a_inside = threading.Event()
    release_a = threading.Event()
    real_record = audit_mod.record
    calls = []

    def paused_record(db, actor, action, rtype, rid=None, meta=None):
        calls.append(action)
        if len(calls) == 1:  # first request to reach audit is A (B has not started yet)
            a_inside.set()  # A has counted 4 and inserted, transaction still open
            assert release_a.wait(10)
        return real_record(db, actor, action, rtype, rid, meta)

    monkeypatch.setattr(profiles_mod.audit, "record", paused_record)
    results = {}

    def go(name, i):
        c = TestClient(app)  # separate client, separate DB connection per request
        results[name] = c.post("/me/emergency-contacts", json=_contact(i), headers=a)

    ta = threading.Thread(target=go, args=("A", 5), name="req-A")
    tb = threading.Thread(target=go, args=("B", 6), name="req-B")
    ta.start()
    assert a_inside.wait(10)
    tb.start()
    tb.join(0.5)
    assert tb.is_alive(), "B must block on the write reservation while A holds it"
    release_a.set()
    ta.join(10); tb.join(10)

    assert results["A"].status_code == 201
    assert results["B"].status_code == 409
    assert results["B"].json()["detail"] == profiles_mod.QUOTA_REJECTION
    with SessionLocal() as db:
        rows = db.scalars(select(EmergencyContact)).all()
        creates = db.scalars(select(AuditEvent).where(
            AuditEvent.action == "profile.create",
            AuditEvent.resource_type == "emergency_contact")).all()
    assert len(rows) == 5
    assert "+923000000006" not in {r.phone for r in rows}
    assert len(creates) == 5 and {e.resource_id for e in creates} == {str(r.id) for r in rows}


@pytest.mark.parametrize("phone", ["-------", "1------", "(((   )))", "123456",
                                   "1234567890123456", "92+3000000001", "++923000000001",
                                   "+92 300 +0000001", "0300-000000a", ""])
def test_phone_rejected(client, phone):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    r = client.post("/me/emergency-contacts", json={**CONTACT, "phone": phone}, headers=a)
    assert r.status_code == 422, phone


@pytest.mark.parametrize("phone,canonical", [
    ("+92 300 0000001", "+923000000001"), ("(0300) 000-0001", "03000000001"),
    ("1234567", "1234567"), ("+123456789012345", "+123456789012345"),
    ("  030.0000.0001 ", "03000000001")])
def test_phone_canonical_on_create_and_update(client, phone, canonical):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    r = client.post("/me/emergency-contacts", json={**CONTACT, "phone": phone}, headers=a)
    assert r.status_code == 201 and r.json()["phone"] == canonical
    cid = r.json()["id"]
    r = client.put(f"/me/emergency-contacts/{cid}", json={**CONTACT, "phone": "-------"}, headers=a)
    assert r.status_code == 422
    r = client.put(f"/me/emergency-contacts/{cid}", json={**CONTACT, "phone": phone}, headers=a)
    assert r.status_code == 200 and r.json()["phone"] == canonical


@pytest.mark.parametrize("field", ["name", "relationship"])
def test_whitespace_only_names_rejected(client, field):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    assert client.post("/me/emergency-contacts", json={**CONTACT, field: "   "},
                       headers=a).status_code == 422
    r = client.post("/me/emergency-contacts", json={**CONTACT, field: "  Trimmed  "}, headers=a)
    assert r.status_code == 201 and r.json()[field] == "Trimmed"


def test_equivalent_phone_duplicate_policy(client):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")
    b = member(client, "bilal.demo@example.com", "Bilal Demo")
    assert client.post("/me/emergency-contacts", json=CONTACT, headers=a).status_code == 201
    r = client.post("/me/emergency-contacts", json={**CONTACT, "phone": "+92-300-000-0001"},
                    headers=a)
    assert r.status_code == 409 and r.json()["detail"] == profiles_mod.DUPLICATE_PHONE
    # Different users may list the same number.
    assert client.post("/me/emergency-contacts", json=CONTACT, headers=b).status_code == 201
    other = client.post("/me/emergency-contacts", json=_contact(9), headers=a).json()
    r = client.put(f"/me/emergency-contacts/{other['id']}", json=CONTACT, headers=a)
    assert r.status_code == 409


def test_audit_failure_rolls_back_domain_write(client, monkeypatch):
    a = member(client, "ayesha.demo@example.com", "Ayesha Demo")

    def boom(*args, **kwargs):
        raise RuntimeError("injected audit insert failure")

    monkeypatch.setattr(profiles_mod.audit, "record", boom)
    c = TestClient(app, raise_server_exceptions=False)
    assert c.put("/me/demographic", json=DEMO, headers=a).status_code == 500
    assert c.post("/me/emergency-contacts", json=CONTACT, headers=a).status_code == 500
    with SessionLocal() as db:
        assert db.scalars(select(Demographic)).all() == []
        assert db.scalars(select(EmergencyContact)).all() == []
        assert db.scalars(select(AuditEvent).where(
            AuditEvent.action.like("profile.%"))).all() == []
