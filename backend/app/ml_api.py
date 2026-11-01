"""Week 3 educational ML + FAQ endpoints (fictional synthetic data only)."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ml import faq

ART = Path(__file__).resolve().parent.parent / "ml" / "artifacts"
DISCLAIMER = ("Fictional educational demo built on synthetic data. Not medical advice, "
              "diagnosis, triage, or treatment.")

router = APIRouter(prefix="/api/v1", tags=["week3-ml"])


@lru_cache
def _model() -> dict:
    path = ART / "engagement_model.joblib"
    if not path.exists():
        raise HTTPException(503, "Model artifact missing. Run: python -m scripts.train_ml")
    return joblib.load(path)


class PredictIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    age: int = Field(ge=18, le=100)
    sessions_last_30d: int = Field(ge=0, le=60)
    avg_session_minutes: float = Field(ge=0, le=240)
    days_since_signup: int = Field(ge=0, le=3650)
    reminders_opt_in: bool
    preferred_channel: Literal["email", "sms", "app"]


class FaqIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=500)


@router.post("/predict")
def predict(body: PredictIn):
    m = _model()
    row = body.model_dump()
    row["reminders_opt_in"] = int(row["reminders_opt_in"])
    X = pd.DataFrame([row])[m["features"]]
    proba = float(m["pipeline"].predict_proba(X)[0][1])
    return {"prediction": "likely_engaged" if proba >= 0.5 else "unlikely_engaged",
            "probability": round(proba, 4), "model_version": m["model_version"],
            "estimator": m["estimator"], "disclaimer": DISCLAIMER}


@router.get("/model")
def model_info():
    return {**json.loads((ART / "metrics.json").read_text()), "disclaimer": DISCLAIMER}


@router.get("/clusters")
def clusters():
    return {**json.loads((ART / "clusters.json").read_text()), "disclaimer": DISCLAIMER}


@router.post("/faq")
def faq_answer(body: FaqIn):
    return {**faq.answer(body.question), "policy_version": faq.corpus()["policy_version"],
            "disclaimer": DISCLAIMER}
