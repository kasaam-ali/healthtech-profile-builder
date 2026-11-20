"""PR #4 review item 2: invalid model/report artifacts give a controlled, generic 503.

Each test points the router at a temporary copy of the real artifacts, breaks one
file, checks the 503, then restores a good file and checks recovery without a
restart (invalid loads are never cached).
"""
import json
import logging
import shutil

import joblib
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.pipeline import Pipeline

from app import ml_api
from ml.dataset import FEATURES

GOOD = {"age": 34, "sessions_last_30d": 12, "avg_session_minutes": 20.5,
        "days_since_signup": 120, "reminders_opt_in": True, "preferred_channel": "app"}
REAL = ml_api.ART


@pytest.fixture()
def art(tmp_path, monkeypatch):
    for f in ("engagement_model.joblib", "metrics.json", "clusters.json", "pca_clusters.png"):
        shutil.copy(REAL / f, tmp_path / f)
    monkeypatch.setattr(ml_api, "ART", tmp_path)
    ml_api.reset_artifact_cache()
    yield tmp_path
    ml_api.reset_artifact_cache()


def _predict(client):
    return client.post("/api/v1/predict", json=GOOD)


def _assert_generic_503(r):
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "temporarily unavailable" in detail
    # Generic for the client: no paths, exception names or training commands.
    for leak in ("Traceback", "joblib", ".json", "/", "Error", "train_ml"):
        assert leak not in detail


def _restore(art, name):
    # os.replace semantics: a new file swapped in, like a redeploy would do.
    tmp = art / (name + ".new")
    shutil.copy(REAL / name, tmp)
    tmp.replace(art / name)


def test_good_artifacts_load(client, art):
    assert _predict(client).status_code == 200
    assert client.get("/api/v1/model").status_code == 200
    assert client.get("/api/v1/clusters").status_code == 200


def test_missing_model_503_then_recovers(client, art):
    (art / "engagement_model.joblib").unlink()
    _assert_generic_503(_predict(client))
    _restore(art, "engagement_model.joblib")
    assert _predict(client).status_code == 200


@pytest.mark.parametrize("payload", [b"", b"not a joblib file at all", b"\x80\x04\x95garbage"])
def test_damaged_model_503_then_recovers(client, art, caplog, payload):
    (art / "engagement_model.joblib").write_bytes(payload)
    with caplog.at_level(logging.ERROR, logger="app.ml_api"):
        _assert_generic_503(_predict(client))
    assert any("engagement_model.joblib" in r.getMessage() for r in caplog.records)
    _restore(art, "engagement_model.joblib")
    assert _predict(client).status_code == 200


def test_truncated_model_503(client, art):
    raw = (REAL / "engagement_model.joblib").read_bytes()
    (art / "engagement_model.joblib").write_bytes(raw[: len(raw) // 2])
    _assert_generic_503(_predict(client))


def _valid_dict():
    return joblib.load(REAL / "engagement_model.joblib")


@pytest.mark.parametrize("mutate", [
    lambda d: {},
    lambda d: {k: v for k, v in d.items() if k != "features"},
    lambda d: {k: v for k, v in d.items() if k != "model_version"},
    lambda d: {**d, "features": list(reversed(FEATURES))},
    lambda d: {**d, "features": FEATURES[:-1]},
    lambda d: {**d, "estimator": "mystery_model"},
    lambda d: {**d, "model_version": 3},
    lambda d: {**d, "pipeline": "not a pipeline"},
    lambda d: ["pipeline", "features"],
], ids=["empty", "no-features", "no-version", "feature-order", "feature-missing",
        "bad-estimator", "bad-version", "no-pipeline", "not-a-dict"])
def test_incomplete_or_wrong_contract_503(client, art, mutate):
    joblib.dump(mutate(_valid_dict()), art / "engagement_model.joblib")
    _assert_generic_503(_predict(client))
    _restore(art, "engagement_model.joblib")
    assert _predict(client).status_code == 200


def test_wrong_class_mapping_503(client, art):
    d = _valid_dict()
    pipe = Pipeline([("prep", d["pipeline"].named_steps["prep"]),
                     ("clf", DummyClassifier(strategy="most_frequent"))])
    import pandas as pd
    X = pd.DataFrame([ml_api.PROBE_ROW] * 4)[FEATURES]
    pipe.fit(X, ["yes", "no", "yes", "no"])  # classes_ ['no', 'yes'], not [0, 1]
    joblib.dump({**d, "pipeline": pipe}, art / "engagement_model.joblib")
    _assert_generic_503(_predict(client))


def test_invalid_load_is_not_cached_and_valid_load_is(client, art):
    (art / "engagement_model.joblib").write_bytes(b"broken")
    _assert_generic_503(_predict(client))
    assert "engagement_model.joblib" not in ml_api._cache
    _restore(art, "engagement_model.joblib")
    assert _predict(client).status_code == 200
    assert "engagement_model.joblib" in ml_api._cache
    # Breaking a cached good file is detected on the next request, not served stale.
    (art / "engagement_model.joblib").write_bytes(b"broken again")
    _assert_generic_503(_predict(client))
    assert "engagement_model.joblib" not in ml_api._cache


REPORTS = [("metrics.json", "/api/v1/model"), ("clusters.json", "/api/v1/clusters")]


@pytest.mark.parametrize("name,url", REPORTS)
@pytest.mark.parametrize("content", [None, "", "{not json", "[]", '{"k": 3}', "null"],
                         ids=["missing", "empty", "malformed", "array", "partial", "null"])
def test_bad_report_503_then_recovers(client, art, name, url, content):
    if content is None:
        (art / name).unlink()
    else:
        (art / name).write_text(content)
    _assert_generic_503(client.get(url))
    _restore(art, name)
    r = client.get(url)
    assert r.status_code == 200 and "disclaimer" in r.json()


def test_metrics_with_wrong_types_503(client, art):
    m = json.loads((REAL / "metrics.json").read_text())
    m["test_results"][m["chosen_estimator"]]["f1"] = "high"
    (art / "metrics.json").write_text(json.dumps(m))
    _assert_generic_503(client.get("/api/v1/model"))


def test_clusters_count_mismatch_503(client, art):
    c = json.loads((REAL / "clusters.json").read_text())
    c["clusters"] = c["clusters"][:1]
    (art / "clusters.json").write_text(json.dumps(c))
    _assert_generic_503(client.get("/api/v1/clusters"))


def test_plot_served_as_png(client, art):
    r = client.get("/api/v1/clusters/plot")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG")


@pytest.mark.parametrize("content", [None, b"<html>not a png</html>"])
def test_plot_missing_or_invalid_503(client, art, content):
    if content is None:
        (art / "pca_clusters.png").unlink()
    else:
        (art / "pca_clusters.png").write_bytes(content)
    _assert_generic_503(client.get("/api/v1/clusters/plot"))
    _restore(art, "pca_clusters.png")
    assert client.get("/api/v1/clusters/plot").status_code == 200
