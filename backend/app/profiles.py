"""Week 2 profile routes.

Member routes (/me/*) use Bearer JWT and always scope queries by current_user.id;
the client never supplies user_id. Admin routes use the server-side admin session only.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import audit, schemas
from .db import get_db
from .deps import current_admin, current_user
from .models import Demographic, EmergencyContact, User, WellnessPreference

MAX_EMERGENCY_CONTACTS = 5

router = APIRouter()


def _changed_fields(obj, data: dict) -> list[str]:
    return sorted(k for k, v in data.items() if getattr(obj, k) != v)


# ---------- Demographic (1:1 upsert) ----------
@router.get("/me/demographic", response_model=schemas.DemographicOut)
def get_demographic(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(Demographic).where(Demographic.user_id == user.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No demographic section yet")
    return row


@router.put("/me/demographic", response_model=schemas.DemographicOut)
def put_demographic(body: schemas.DemographicIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    data = body.model_dump()
    row = db.scalar(select(Demographic).where(Demographic.user_id == user.id))
    action = "profile.update" if row else "profile.create"
    if row is None:
        row = Demographic(user_id=user.id)
        db.add(row)
        changed = sorted(k for k, v in data.items() if v is not None)
    else:
        changed = _changed_fields(row, data)
    for k, v in data.items():
        setattr(row, k, v)
    db.flush()
    audit.record(db, user.id, action, "demographic", row.id, {"fields": changed})
    db.commit()
    db.refresh(row)
    return row


@router.delete("/me/demographic", status_code=204)
def delete_demographic(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(Demographic).where(Demographic.user_id == user.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No demographic section yet")
    audit.record(db, user.id, "profile.delete", "demographic", row.id)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


# ---------- Wellness preference (1:1 upsert) ----------
@router.get("/me/wellness", response_model=schemas.WellnessOut)
def get_wellness(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(WellnessPreference).where(WellnessPreference.user_id == user.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No wellness section yet")
    return row


@router.put("/me/wellness", response_model=schemas.WellnessOut)
def put_wellness(body: schemas.WellnessIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    data = body.model_dump()
    row = db.scalar(select(WellnessPreference).where(WellnessPreference.user_id == user.id))
    action = "profile.update" if row else "profile.create"
    if row is None:
        row = WellnessPreference(user_id=user.id)
        db.add(row)
        changed = sorted(data)
    else:
        changed = _changed_fields(row, data)
    for k, v in data.items():
        setattr(row, k, v)
    db.flush()
    audit.record(db, user.id, action, "wellness_preference", row.id, {"fields": changed})
    db.commit()
    db.refresh(row)
    return row


@router.delete("/me/wellness", status_code=204)
def delete_wellness(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(WellnessPreference).where(WellnessPreference.user_id == user.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No wellness section yet")
    audit.record(db, user.id, "profile.delete", "wellness_preference", row.id)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


# ---------- Emergency contacts (1:N) ----------
def _own_contact(db: Session, user: User, contact_id: int) -> EmergencyContact:
    # Ownership is part of the query: another user's id looks exactly like a missing id (404).
    row = db.scalar(select(EmergencyContact).where(EmergencyContact.id == contact_id,
                                                   EmergencyContact.user_id == user.id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Emergency contact not found")
    return row


@router.get("/me/emergency-contacts", response_model=list[schemas.EmergencyContactOut])
def list_contacts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(EmergencyContact).where(EmergencyContact.user_id == user.id)
                      .order_by(EmergencyContact.id)).all()


@router.post("/me/emergency-contacts", response_model=schemas.EmergencyContactOut,
             status_code=201)
def create_contact(body: schemas.EmergencyContactIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(EmergencyContact)
                      .where(EmergencyContact.user_id == user.id))
    if count >= MAX_EMERGENCY_CONTACTS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"At most {MAX_EMERGENCY_CONTACTS} emergency contacts allowed")
    row = EmergencyContact(user_id=user.id, **body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user.id, "profile.create", "emergency_contact", row.id)
    db.commit()
    db.refresh(row)
    return row


@router.get("/me/emergency-contacts/{contact_id}", response_model=schemas.EmergencyContactOut)
def get_contact(contact_id: int, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    return _own_contact(db, user, contact_id)


@router.put("/me/emergency-contacts/{contact_id}", response_model=schemas.EmergencyContactOut)
def update_contact(contact_id: int, body: schemas.EmergencyContactIn,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _own_contact(db, user, contact_id)
    data = body.model_dump()
    changed = _changed_fields(row, data)
    for k, v in data.items():
        setattr(row, k, v)
    audit.record(db, user.id, "profile.update", "emergency_contact", row.id, {"fields": changed})
    db.commit()
    db.refresh(row)
    return row


@router.delete("/me/emergency-contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: int, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    row = _own_contact(db, user, contact_id)
    audit.record(db, user.id, "profile.delete", "emergency_contact", row.id)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


# ---------- Admin search (session auth only) ----------
@router.get("/admin/profiles", response_model=schemas.AdminProfilePage)
def admin_search_profiles(
    q: str | None = Query(default=None, max_length=100, description="email or name contains"),
    city: str | None = Query(default=None, max_length=100, description="exact city match"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(current_admin),
    db: Session = Depends(get_db),
):
    contacts = (select(EmergencyContact.user_id, func.count().label("n"))
                .group_by(EmergencyContact.user_id).subquery())
    base = (select(User, Demographic, WellnessPreference, contacts.c.n)
            .outerjoin(Demographic, Demographic.user_id == User.id)
            .outerjoin(WellnessPreference, WellnessPreference.user_id == User.id)
            .outerjoin(contacts, contacts.c.user_id == User.id)
            .where(User.is_admin.is_(False)))
    if q:
        like = f"%{q.strip().lower()}%"
        base = base.where(or_(func.lower(User.email).like(like),
                              func.lower(User.full_name).like(like)))
    if city:
        base = base.where(Demographic.city == city.strip())
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(User.id).offset((page - 1) * page_size).limit(page_size)).all()
    # Log the access with filter keys only (not values) to avoid copying PII into the audit log.
    audit.record(db, admin.id, "admin.profiles.list", "profile", None,
                 {"filters": sorted(k for k, v in {"q": q, "city": city}.items() if v),
                  "page": page, "result_count": len(rows)})
    db.commit()
    items = [schemas.AdminProfileRow(
        id=u.id, email=u.email, full_name=u.full_name,
        city=d.city if d else None, country=d.country if d else None,
        activity_level=w.activity_level if w else None, emergency_contact_count=n or 0)
        for u, d, w, n in rows]
    return schemas.AdminProfilePage(items=items, total=total, page=page, page_size=page_size)
