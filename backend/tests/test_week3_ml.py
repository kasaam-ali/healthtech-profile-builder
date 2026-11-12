import pytest

GOOD = {"age": 34, "sessions_last_30d": 12, "avg_session_minutes": 20.5,
        "days_since_signup": 120, "reminders_opt_in": True, "preferred_channel": "app"}


def test_predict_happy_path(client):
    r = client.post("/api/v1/predict", json=GOOD)
    assert r.status_code == 200
    d = r.json()
    assert d["prediction"] in {"likely_engaged", "unlikely_engaged"}
    assert 0 <= d["probability"] <= 1
    assert d["model_version"] == "engagement-v1.1.0"
    assert "Not medical advice" in d["disclaimer"]


def test_predict_is_deterministic(client):
    a = client.post("/api/v1/predict", json=GOOD).json()
    b = client.post("/api/v1/predict", json=GOOD).json()
    assert a["probability"] == b["probability"]


@pytest.mark.parametrize("patch", [
    {"age": 5}, {"age": 200}, {"sessions_last_30d": -1}, {"avg_session_minutes": 9999},
    {"days_since_signup": -3}, {"preferred_channel": "fax"}, {"reminders_opt_in": "yes"},
    {"age": "thirty"}, {"diagnosis": "x"},
])
def test_predict_rejects_bad_input(client, patch):
    assert client.post("/api/v1/predict", json={**GOOD, **patch}).status_code == 422


def test_predict_rejects_missing_field(client):
    body = dict(GOOD); body.pop("age")
    assert client.post("/api/v1/predict", json=body).status_code == 422


def test_predict_rejects_non_json(client):
    r = client.post("/api/v1/predict", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_clusters_smoke(client):
    d = client.get("/api/v1/clusters").json()
    assert d["k"] == len(d["clusters"]) == 3
    assert -1 <= d["silhouette"] <= 1
    assert "disclaimer" in d


def test_model_info_has_metrics(client):
    d = client.get("/api/v1/model").json()
    assert set(d["cv_results"]) == {"logistic_regression", "random_forest",
                                    "dummy_always_engaged", "dummy_stratified"}
    assert "training split only" in d["selection"]["method"]
    # Final test report covers only the chosen model and the prevalence baseline.
    assert set(d["test_results"]) == {d["chosen_estimator"], "dummy_always_engaged"}
    assert d["test_results"][d["chosen_estimator"]]["f1"] > d["test_results"]["dummy_always_engaged"]["f1"]
    assert d["model_version"] == "engagement-v1.1.0"
