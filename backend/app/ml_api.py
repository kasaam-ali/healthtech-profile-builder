"""Week 3 educational ML + FAQ endpoints (fictional synthetic data only).

Artifact loading (PR #4 review fix): every model or report file is read at one
loading boundary that catches expected I/O, deserialization and contract
failures, logs the detail server-side, and turns them into a generic 503.
Only artifacts that pass validation are cached, and the cache is keyed on the
file's stat signature, so replacing a bad file with a good one recovers
without a restart.

Trust note: joblib uses pickle, so the model path must only ever hold a file
produced by scripts/train_ml.py from this repository, never an upload.
"""
import json
import logging
import math
import threading
from pathlib import Path
from typing import Any, Callable, Literal

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ml import faq
from ml.dataset import FEATURES

log = logging.getLogger("app.ml_api")

ART = Path(__file__).resolve().parent.parent / "ml" / "artifacts"
MODEL_FILE = "engagement_model.joblib"
METRICS_FILE = "metrics.json"
CLUSTERS_FILE = "clusters.json"
PLOT_FILE = "pca_clusters.png"
ESTIMATORS = {"logistic_regression", "random_forest"}
DISCLAIMER = ("Fictional educational demo built on synthetic data. Not medical advice, "
              "diagnosis, triage, or treatment.")
UNAVAILABLE = {
    MODEL_FILE: "The prediction model is temporarily unavailable. Please try again later.",
    METRICS_FILE: "Model information is temporarily unavailable. Please try again later.",
    CLUSTERS_FILE: "Cluster summary is temporarily unavailable. Please try again later.",
    PLOT_FILE: "Cluster plot is temporarily unavailable. Please try again later.",
}
# A fixed in-range synthetic row used to smoke-test a loaded pipeline.
PROBE_ROW = {"age": 40, "sessions_last_30d": 6, "avg_session_minutes": 15.0,
             "days_since_signup": 300, "reminders_opt_in": 1, "preferred_channel": "app"}

router = APIRouter(prefix="/api/v1", tags=["week3-ml"])


class ArtifactError(Exception):
    """An artifact exists in an unusable state. Message is for server logs only."""


_cache: dict[str, tuple[tuple, Any]] = {}
_lock = threading.Lock()


def reset_artifact_cache() -> None:
    with _lock:
        _cache.clear()


def _signature(path: Path) -> tuple:
    st = path.stat()  # FileNotFoundError is handled by the caller
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _load(name: str, reader: Callable[[Path], Any], validate: Callable[[Any], None]) -> Any:
    path = ART / name
    try:
        sig = _signature(path)
        with _lock:
            hit = _cache.get(name)
        if hit and hit[0] == sig:
            return hit[1]
        value = reader(path)
        validate(value)
    except Exception as exc:  # noqa: BLE001  load boundary: every failure becomes a 503
        log.error("ML artifact %s unavailable: %s: %s", path, type(exc).__name__, exc)
        with _lock:
            _cache.pop(name, None)  # never keep a stale or invalid entry
        raise HTTPException(503, UNAVAILABLE[name]) from None
    with _lock:
        _cache[name] = (sig, value)
    return value


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ArtifactError(msg)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate_model(art: Any) -> None:
    _require(isinstance(art, dict), "model artifact is not a dict")
    missing = {"pipeline", "features", "model_version", "estimator"} - set(art)
    _require(not missing, f"model artifact missing keys {sorted(missing)}")
    _require(art["features"] == FEATURES, "feature schema does not match ml.dataset.FEATURES")
    _require(isinstance(art["model_version"], str) and art["model_version"].startswith("engagement-v"),
             "model_version is missing or malformed")
    _require(art["estimator"] in ESTIMATORS, f"unknown estimator {art['estimator']!r}")
    pipe = art["pipeline"]
    _require(hasattr(pipe, "predict_proba"), "pipeline has no predict_proba")
    classes = list(getattr(pipe, "classes_", []))
    _require(classes == [0, 1], f"class mapping must be [0, 1], got {classes}")
    proba = np.asarray(pipe.predict_proba(pd.DataFrame([PROBE_ROW])[FEATURES]))
    _require(proba.shape == (1, 2) and np.isfinite(proba).all()
             and abs(float(proba.sum()) - 1.0) < 1e-6, "probe prediction is not a valid probability pair")


def validate_metrics(m: Any) -> None:
    _require(isinstance(m, dict), "metrics.json is not an object")
    for key in ("model_version", "chosen_estimator"):
        _require(isinstance(m.get(key), str), f"metrics.json missing {key}")
    _require(isinstance(m.get("selection"), dict) and isinstance(m["selection"].get("method"), str),
             "metrics.json missing selection.method")
    cv, test = m.get("cv_results"), m.get("test_results")
    _require(isinstance(cv, dict) and cv, "metrics.json missing cv_results")
    for name, r in cv.items():
        _require(isinstance(r, dict) and all(_is_num(r.get(k)) for k in
                 ("f1_mean", "f1_std", "precision_mean", "recall_mean", "accuracy_mean")),
                 f"cv_results[{name}] malformed")
    _require(isinstance(test, dict) and m["chosen_estimator"] in test, "metrics.json missing test_results")
    for name, r in test.items():
        cm = r.get("confusion_matrix") if isinstance(r, dict) else None
        _require(all(_is_num(r.get(k)) for k in ("precision", "recall", "f1", "accuracy"))
                 and isinstance(cm, list) and len(cm) == 2
                 and all(isinstance(row, list) and len(row) == 2 and all(isinstance(v, int) for v in row)
                         for row in cm), f"test_results[{name}] malformed")


def validate_clusters(c: Any) -> None:
    _require(isinstance(c, dict), "clusters.json is not an object")
    _require(isinstance(c.get("k"), int) and c["k"] > 0, "clusters.json k malformed")
    _require(_is_num(c.get("silhouette")) and -1 <= c["silhouette"] <= 1, "silhouette malformed")
    items = c.get("clusters")
    _require(isinstance(items, list) and len(items) == c["k"], "clusters list does not match k")
    for it in items:
        _require(isinstance(it, dict) and isinstance(it.get("cluster_id"), int)
                 and isinstance(it.get("size"), int) and isinstance(it.get("means"), dict)
                 and all(_is_num(v) for v in it["means"].values()), "cluster entry malformed")


def validate_png(data: Any) -> None:
    _require(isinstance(data, bytes) and data.startswith(b"\x89PNG\r\n\x1a\n"), "plot is not a PNG")


def _model() -> dict:
    return _load(MODEL_FILE, joblib.load, validate_model)


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
    try:
        proba = float(m["pipeline"].predict_proba(pd.DataFrame([row])[m["features"]])[0][1])
    except Exception as exc:  # noqa: BLE001  validated input, so this is a model fault
        log.error("Prediction failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(503, UNAVAILABLE[MODEL_FILE]) from None
    return {"prediction": "likely_engaged" if proba >= 0.5 else "unlikely_engaged",
            "probability": round(proba, 4), "model_version": m["model_version"],
            "estimator": m["estimator"], "disclaimer": DISCLAIMER}


@router.get("/model")
def model_info():
    return {**_load(METRICS_FILE, _read_json, validate_metrics), "disclaimer": DISCLAIMER}


@router.get("/clusters")
def clusters():
    return {**_load(CLUSTERS_FILE, _read_json, validate_clusters), "disclaimer": DISCLAIMER}


@router.get("/clusters/plot", response_class=FileResponse)
def clusters_plot():
    _load(PLOT_FILE, lambda p: p.read_bytes()[:8], validate_png)
    return FileResponse(ART / PLOT_FILE, media_type="image/png",
                        headers={"Cache-Control": "no-cache"})


@router.post("/faq")
def faq_answer(body: FaqIn):
    return {**faq.answer(body.question), "policy_version": faq.corpus()["policy_version"],
            "disclaimer": DISCLAIMER}
