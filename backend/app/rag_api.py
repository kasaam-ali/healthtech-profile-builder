"""Week 4: RAG FAQ with citations and typed low-risk tools.

Read tools: search_approved_documents, check_appointment_availability (no auth needed;
actor recorded when a valid JWT is present). Mock write tool: request_appointment_hold
requires a member JWT AND human_confirmed=true in the body, checked server-side.
Every call writes an audit_events row (no secrets, no question text, only metadata).
"""
import json
import re
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ml import rag

from . import audit
from .config import settings
from .db import get_db
from .deps import bearer, current_user
from .models import AppointmentHold, User
from .security import decode_token

DISCLAIMER = ("Fictional demo clinic. Answers come only from approved fictional policy "
              "documents. Not medical advice, diagnosis, triage, or treatment.")
MAX_ACTIVE_HOLDS = 2

router = APIRouter(prefix="/api/v2", tags=["week4-rag-tools"])


def optional_user_id(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int | None:
    return decode_token(creds.credentials, "access") if creds else None


def _sim(flag: bool) -> bool:
    # Failure simulation is a dev/test aid only; ignored in production.
    return flag and not settings.is_production


def _log(db: Session, actor: int | None, action: str, tool: str, meta: dict) -> None:
    audit.record(db, actor, action, "tool", tool, meta)
    db.commit()


@lru_cache
def schedule() -> dict:
    return json.loads((rag.DOCS_DIR / "schedule.json").read_text(encoding="utf-8"))


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


def _unavailable(db, actor, tool, exc) -> HTTPException:
    _log(db, actor, "tool.failed", tool, {"error": type(exc).__name__})
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                         "Document retrieval is temporarily unavailable. Please try again.")


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
    held = set(db.scalars(select(AppointmentHold.slot_id)))
    slots = [s for s in schedule()["slots"]
             if s["status"] == "open" and s["slot_id"] not in held
             and (body.date is None or s["date"] == body.date)
             and (body.coach is None or body.coach.lower() in s["coach"].lower())]
    _log(db, actor, "tool.call", "check_appointment_availability",
         {"filters": [k for k, v in body.model_dump().items() if v], "count": len(slots)})
    return {"tool": "check_appointment_availability", "slots": slots, "disclaimer": DISCLAIMER}


@router.post("/tools/request_appointment_hold", status_code=201)
def request_appointment_hold(body: HoldIn, db: Session = Depends(get_db),
                             user: User = Depends(current_user)):
    tool = "request_appointment_hold"
    if not body.human_confirmed:
        _log(db, user.id, "tool.denied", tool, {"reason": "no_human_confirmation"})
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Explicit confirmation required: set human_confirmed=true.")
    slot = next((s for s in schedule()["slots"] if s["slot_id"] == body.slot_id), None)
    if slot is None or slot["status"] != "open":
        _log(db, user.id, "tool.denied", tool, {"reason": "slot_unavailable"})
        raise HTTPException(status.HTTP_409_CONFLICT, "Slot is not open.")
    active = db.scalar(select(func.count()).select_from(AppointmentHold)
                       .where(AppointmentHold.user_id == user.id,
                              AppointmentHold.status == "held"))
    if active >= MAX_ACTIVE_HOLDS:
        _log(db, user.id, "tool.denied", tool, {"reason": "hold_limit"})
        raise HTTPException(status.HTTP_409_CONFLICT, f"At most {MAX_ACTIVE_HOLDS} active holds.")
    hold = AppointmentHold(user_id=user.id, slot_id=body.slot_id, status="held")
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
    db.refresh(hold)
    return {"tool": tool, "hold_id": hold.id, "slot_id": hold.slot_id, "status": hold.status,
            "note": "Hold is a request only; staff confirm within 24 hours (fictional)."}


@router.get("/tools/my_holds")
def my_holds(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(AppointmentHold).where(AppointmentHold.user_id == user.id))
    return [{"hold_id": h.id, "slot_id": h.slot_id, "status": h.status} for h in rows]
