"""Week 4: RAG FAQ with citations and typed low-risk tools.

Read tools: search_approved_documents, check_appointment_availability (no auth needed;
actor recorded when a valid JWT is present). Mock write tool: request_appointment_hold
requires a member JWT AND human_confirmed=true in the body, checked server-side.
Every call writes an audit_events row (no secrets, no question text, only metadata).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ml import rag

from . import audit
from .config import settings
from .db import get_db
from .deps import bearer, current_user
from .models import AppointmentHold, User
from .security import decode_token

logger = logging.getLogger(__name__)

DISCLAIMER = ("Fictional demo clinic. Answers come only from approved fictional policy "
              "documents. Not medical advice, diagnosis, triage, or treatment.")
MAX_ACTIVE_HOLDS = 2
HOLD_DURATION_HOURS = 24
HOLD_DURATION = timedelta(hours=HOLD_DURATION_HOURS)


def _system_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Injectable clock for unit tests and reproducible temporal simulations
clock: Callable[[], datetime] = _system_now


def get_now() -> datetime:
    return clock()


router = APIRouter(prefix="/api/v2", tags=["week4-rag-tools"])


def optional_user_id(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int | None:
    return decode_token(creds.credentials, "access") if creds else None


def _sim(flag: bool) -> bool:
    # Failure simulation is a dev/test aid only; ignored in production.
    return flag and not settings.is_production


def _log(db: Session, actor: int | None, action: str, tool: str, meta: dict) -> None:
    audit.record(db, actor, action, "tool", tool, meta)
    db.commit()


def _begin_write_reservation(db: Session) -> None:
    """Take the SQLite write reservation before counting/inserting hold quotas.
    Serializes concurrent requests to prevent race condition over-allocations."""
    raw = db.connection().connection.dbapi_connection
    if getattr(raw, "in_transaction", False):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Calendar is busy, please retry")
    try:
        raw.execute("BEGIN IMMEDIATE")
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Calendar is busy, please retry") from exc


class ScheduleError(RuntimeError):
    """Raised when schedule file is missing or malformed."""


SCHEDULE_PATH = rag.DOCS_DIR / "schedule.json"
_cached_schedule_key: tuple | None = None
_cached_schedule_data: dict | None = None


def load_schedule(path: Path | None = None) -> dict:
    """Validated schedule loading with mtime-based caching.
    Invalid, corrupt or missing schedule raises ScheduleError."""
    global _cached_schedule_key, _cached_schedule_data
    if path is None:
        path = SCHEDULE_PATH

    if not path.is_file():
        raise ScheduleError("Schedule file not found")

    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
        if _cached_schedule_key == key and _cached_schedule_data is not None:
            return _cached_schedule_data

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or "slots" not in data or not isinstance(data["slots"], list):
            raise ScheduleError("Schedule schema invalid: missing slots array")
        for s in data["slots"]:
            if not isinstance(s, dict) or "slot_id" not in s or "status" not in s:
                raise ScheduleError("Schedule slot record malformed")
        _cached_schedule_key = key
        _cached_schedule_data = data
        return data
    except json.JSONDecodeError as exc:
        raise ScheduleError(f"Schedule JSON malformed: {type(exc).__name__}") from exc
    except Exception as exc:
        if isinstance(exc, ScheduleError):
            raise
        raise ScheduleError(f"Schedule error: {type(exc).__name__}") from exc


def schedule() -> dict:
    return load_schedule()


def expire_stale_holds(db: Session, now: datetime | None = None) -> int:
    """Expires any active holds older than 24 hours."""
    if now is None:
        now = get_now()
    cutoff = now - HOLD_DURATION
    stmt = (
        update(AppointmentHold)
        .where(AppointmentHold.status == "held", AppointmentHold.created_at < cutoff)
        .values(status="expired")
    )
    res = db.execute(stmt)
    return res.rowcount


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaqIn(Strict):
    question: str = Field(min_length=3, max_length=500)
    setting: Literal["baseline", "tuned"] = rag.DEFAULT_SETTING
    simulate_provider_timeout: bool = False


class SearchIn(Strict):
    query: str = Field(min_length=2, max_length=300)
    top_k: int = Field(default=3, ge=1, le=5)


class AvailabilityIn(Strict):
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    coach: str | None = Field(default=None, max_length=60)


class HoldIn(Strict):
    slot_id: str = Field(min_length=3, max_length=40)
    human_confirmed: bool = False
    simulate_provider_timeout: bool = False

    @field_validator("slot_id")
    @classmethod
    def _shape(cls, v: str) -> str:
        if not re.fullmatch(r"S-\d{4}-\d{2}-\d{2}-\d{4}", v):
            raise ValueError("slot_id must look like S-YYYY-MM-DD-HHMM")
        return v


class ReleaseIn(Strict):
    hold_id: int | None = None
    slot_id: str | None = None


def _unavailable(db: Session, actor: int | None, tool: str, exc: Exception,
                 msg: str = "Document retrieval is temporarily unavailable. Please try again.") -> HTTPException:
    err_class = type(exc).__name__
    logger.error("Tool %s failed: %s", tool, err_class)
    _log(db, actor, "tool.failed", tool, {"error": err_class})
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)


@router.post("/faq")
def faq(body: FaqIn, db: Session = Depends(get_db), actor: int | None = Depends(optional_user_id)):
    try:
        out = rag.answer(body.question, body.setting,
                         simulate_failure=_sim(body.simulate_provider_timeout))
    except rag.RetrievalError as exc:
        raise _unavailable(db, actor, "rag_faq", exc)
    _log(db, actor, "rag.answer", "rag_faq",
         {"setting": body.setting, "abstained": out["abstained"], "reason": out["reason"],
          "refs": [c["chunk_id"] for c in out["citations"]], "question_len": len(body.question)})
    return {**out, "disclaimer": DISCLAIMER}


@router.post("/tools/search_approved_documents")
def search_approved_documents(body: SearchIn, db: Session = Depends(get_db),
                              actor: int | None = Depends(optional_user_id)):
    if rag.INJECTION.search(body.query):
        _log(db, actor, "tool.denied", "search_approved_documents", {"reason": "prompt_injection"})
        return {"tool": "search_approved_documents", "results": [], "refused": "prompt_injection"}
    try:
        hits = rag.retrieve(body.query)[: body.top_k]
    except rag.RetrievalError as exc:
        raise _unavailable(db, actor, "search_approved_documents", exc)
    _log(db, actor, "tool.call", "search_approved_documents",
         {"refs": [h["chunk_id"] for h in hits], "top_k": body.top_k})
    return {"tool": "search_approved_documents", "results": hits, "refused": None}


@router.post("/tools/check_appointment_availability")
def check_appointment_availability(body: AvailabilityIn, db: Session = Depends(get_db),
                                   actor: int | None = Depends(optional_user_id)):
    tool = "check_appointment_availability"
    try:
        sched = load_schedule()
    except ScheduleError as exc:
        raise _unavailable(db, actor, tool, exc,
                           "Appointment schedule is temporarily unavailable. Please try again.")

    cutoff = get_now() - HOLD_DURATION
    held = set(db.scalars(
        select(AppointmentHold.slot_id)
        .where(AppointmentHold.status == "held", AppointmentHold.created_at >= cutoff)
    ))
    slots = [s for s in sched["slots"]
             if s["status"] == "open" and s["slot_id"] not in held
             and (body.date is None or s["date"] == body.date)
             and (body.coach is None or body.coach.lower() in s["coach"].lower())]
    _log(db, actor, "tool.call", tool,
         {"filters": [k for k, v in body.model_dump().items() if v], "count": len(slots)})
    return {"tool": tool, "slots": slots, "disclaimer": DISCLAIMER}


@router.post("/tools/request_appointment_hold", status_code=201)
def request_appointment_hold(body: HoldIn, db: Session = Depends(get_db),
                             user: User = Depends(current_user)):
    tool = "request_appointment_hold"
    if not body.human_confirmed:
        _log(db, user.id, "tool.denied", tool, {"reason": "no_human_confirmation"})
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Explicit confirmation required: set human_confirmed=true.")

    try:
        sched = load_schedule()
    except ScheduleError as exc:
        raise _unavailable(db, user.id, tool, exc,
                           "Appointment schedule is temporarily unavailable. Please try again.")

    slot = next((s for s in sched["slots"] if s["slot_id"] == body.slot_id), None)
    if slot is None or slot["status"] != "open":
        _log(db, user.id, "tool.denied", tool, {"reason": "slot_unavailable"})
        raise HTTPException(status.HTTP_409_CONFLICT, "Slot is not open.")

    # 1. Acquire SQLite write reservation BEFORE checking quotas or active holds
    _begin_write_reservation(db)

    now = get_now()
    # Expire stale holds so quota and availability reflect the 24h expiration policy
    expire_stale_holds(db, now)

    cutoff = now - HOLD_DURATION
    already_held = db.scalar(
        select(AppointmentHold)
        .where(AppointmentHold.slot_id == body.slot_id,
               AppointmentHold.status == "held",
               AppointmentHold.created_at >= cutoff)
    )
    if already_held is not None:
        db.rollback()
        _log(db, user.id, "tool.denied", tool, {"reason": "slot_already_held"})
        raise HTTPException(status.HTTP_409_CONFLICT, "Slot is already held.")

    active = db.scalar(select(func.count()).select_from(AppointmentHold)
                       .where(AppointmentHold.user_id == user.id,
                              AppointmentHold.status == "held",
                              AppointmentHold.created_at >= cutoff))
    if active >= MAX_ACTIVE_HOLDS:
        db.rollback()
        _log(db, user.id, "tool.denied", tool, {"reason": "hold_limit"})
        raise HTTPException(status.HTTP_409_CONFLICT, f"At most {MAX_ACTIVE_HOLDS} active holds.")

    hold = AppointmentHold(user_id=user.id, slot_id=body.slot_id, status="held", created_at=now)
    try:
        db.add(hold)
        db.flush()
        if _sim(body.simulate_provider_timeout):
            raise TimeoutError("calendar provider timed out (simulated)")
        audit.record(db, user.id, "tool.approved_write", "tool", tool,
                     {"slot_id": body.slot_id, "confirmed": True})
        db.commit()
    except IntegrityError:
        db.rollback()
        _log(db, user.id, "tool.denied", tool, {"reason": "slot_already_held"})
        raise HTTPException(status.HTTP_409_CONFLICT, "Slot is already held.")
    except TimeoutError as exc:
        db.rollback()  # no partial write survives
        _log(db, user.id, "tool.failed", tool, {"error": type(exc).__name__})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Calendar provider unavailable. No hold was created.")
    except Exception:
        db.rollback()
        raise

    db.refresh(hold)
    return {"tool": tool, "hold_id": hold.id, "slot_id": hold.slot_id, "status": hold.status,
            "note": "Hold is a request only; staff confirm within 24 hours (fictional)."}


@router.post("/tools/release_appointment_hold")
def release_appointment_hold(body: ReleaseIn, db: Session = Depends(get_db),
                             user: User = Depends(current_user)):
    tool = "release_appointment_hold"
    if not body.hold_id and not body.slot_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Must provide hold_id or slot_id.")

    _begin_write_reservation(db)
    now = get_now()
    expire_stale_holds(db, now)

    query = select(AppointmentHold)
    if body.hold_id is not None:
        query = query.where(AppointmentHold.id == body.hold_id)
    else:
        query = query.where(AppointmentHold.slot_id == body.slot_id, AppointmentHold.status == "held")

    hold = db.scalar(query)
    if hold is None or hold.user_id != user.id:
        # Ownership checked: non-existent or other user's hold returns 404
        db.rollback()
        _log(db, user.id, "tool.denied", tool, {"reason": "hold_not_found"})
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment hold not found.")

    if hold.status != "held":
        db.rollback()
        _log(db, user.id, "tool.denied", tool, {"reason": f"already_{hold.status}"})
        raise HTTPException(status.HTTP_409_CONFLICT, f"Hold is already {hold.status}.")

    hold.status = "released"
    audit.record(db, user.id, "tool.approved_write", "tool", tool,
                 {"hold_id": hold.id, "slot_id": hold.slot_id, "action": "released", "status": "released"})
    db.commit()
    db.refresh(hold)
    return {
        "tool": tool,
        "hold_id": hold.id,
        "slot_id": hold.slot_id,
        "status": hold.status,
        "note": "Hold has been released. The slot is now available."
    }


@router.delete("/tools/my_holds/{hold_id}")
def delete_my_hold(hold_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return release_appointment_hold(ReleaseIn(hold_id=hold_id), db=db, user=user)


@router.get("/tools/my_holds")
def my_holds(db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = get_now()
    expire_stale_holds(db, now)
    db.commit()
    rows = db.scalars(select(AppointmentHold)
                      .where(AppointmentHold.user_id == user.id)
                      .order_by(AppointmentHold.created_at.desc())).all()
    cutoff = now - HOLD_DURATION
    out = []
    for h in rows:
        st = h.status
        if st == "held" and h.created_at < cutoff:
            st = "expired"
        out.append({"hold_id": h.id, "slot_id": h.slot_id, "status": st,
                    "created_at": h.created_at.isoformat()})
    return out
