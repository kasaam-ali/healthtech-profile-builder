"""Recreate Week 3 ML artifacts end to end.

Usage (from backend/):  python -m scripts.train_ml

Steps: generate synthetic data, EDA summary, reproducible stratified 75/25
split, then:
- model selection uses 5-fold stratified cross-validation on the TRAINING
  split only (Logistic Regression, Random Forest and two dummy baselines),
  with preprocessing inside each pipeline so every fold is fit on its own
  training folds (no leakage);
- the chosen pipeline is refit on the full training split and scored ONCE on
  the untouched 25% test split, next to an always-engaged (prevalence) dummy baseline, for
  the final report;
- K-Means + PCA on non-sensitive engagement attributes, with a saved plot.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import sklearn

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.dummy import DummyClassifier  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,  # noqa: E402
                             precision_score, recall_score, silhouette_score)
from sklearn.model_selection import (StratifiedKFold, cross_validate,  # noqa: E402
                                     train_test_split)
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from ml.dataset import (BOOLEAN, CATEGORICAL, FEATURES, LABEL, NUMERIC, SEED,  # noqa: E402
                        generate, write_csv)

MODEL_VERSION = "engagement-v1.1.0"
CV_FOLDS = 5
SELECTABLE = ("logistic_regression", "random_forest")
ART = Path(__file__).resolve().parent.parent / "ml" / "artifacts"
CLUSTER_FEATURES = ["sessions_last_30d", "avg_session_minutes", "days_since_signup"]
K = 3


def _matrix(rows, cols):
    return np.array([[r[c] for c in cols] for r in rows], dtype=object)


def preprocessor():
    return ColumnTransformer([
        ("num", StandardScaler(), NUMERIC + BOOLEAN),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])


def main() -> dict:
    ART.mkdir(parents=True, exist_ok=True)
    rows = generate()
    write_csv(rows)
    import pandas as pd  # local import keeps app startup light
    df = pd.DataFrame(rows)
    eda = {
        "rows": len(df),
        "positive_rate": round(float(df[LABEL].mean()), 4),
        "missing_values": int(df.isna().sum().sum()),
        "numeric_summary": json.loads(df[NUMERIC].describe().round(2).to_json()),
    }
    X, y = df[FEATURES], df[LABEL]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=SEED, stratify=y)

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=SEED),
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=8,
                                                random_state=SEED, n_jobs=1),
        # Baselines give the scores context; they are never selectable.
        "dummy_always_engaged": DummyClassifier(strategy="constant", constant=1),
        "dummy_stratified": DummyClassifier(strategy="stratified", random_state=SEED),
    }
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=SEED)
    scoring = ["f1", "precision", "recall", "accuracy"]
    cv_results = {}
    for name, est in candidates.items():
        pipe = Pipeline([("prep", preprocessor()), ("clf", est)])
        s = cross_validate(pipe, X_tr, y_tr, cv=cv, scoring=scoring,
                           error_score="raise")
        cv_results[name] = {
            **{f"{m}_mean": round(float(s[f"test_{m}"].mean()), 4) for m in scoring},
            "f1_std": round(float(s["test_f1"].std()), 4),
        }
    # Selection uses training-only CV F1. The test split is not looked at yet.
    chosen = max(SELECTABLE, key=lambda n: cv_results[n]["f1_mean"])

    def _test_report(name):
        pipe = Pipeline([("prep", preprocessor()), ("clf", candidates[name])]).fit(X_tr, y_tr)
        pred = pipe.predict(X_te)
        return pipe, {
            "precision": round(float(precision_score(y_te, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_te, pred)), 4),
            "f1": round(float(f1_score(y_te, pred)), 4),
            "accuracy": round(float(accuracy_score(y_te, pred)), 4),
            "confusion_matrix": confusion_matrix(y_te, pred, labels=[0, 1]).tolist(),
        }

    final_pipe, chosen_test = _test_report(chosen)
    _, baseline_test = _test_report("dummy_always_engaged")
    test_results = {chosen: chosen_test, "dummy_always_engaged": baseline_test}
    joblib.dump({"pipeline": final_pipe, "model_version": MODEL_VERSION,
                 "estimator": chosen, "features": FEATURES}, ART / "engagement_model.joblib")

    # Clustering on non-sensitive engagement behaviour only (no age, no channel).
    Xc = StandardScaler().fit_transform(df[CLUSTER_FEATURES])
    km = KMeans(n_clusters=K, n_init=10, random_state=SEED).fit(Xc)
    sil = round(float(silhouette_score(Xc, km.labels_)), 4)
    pts = PCA(n_components=2, random_state=SEED).fit_transform(Xc)
    plt.figure(figsize=(6, 4.5))
    plt.scatter(pts[:, 0], pts[:, 1], c=km.labels_, s=8, cmap="viridis")
    plt.title(f"K-Means (k={K}) on synthetic engagement data, PCA 2D")
    plt.xlabel("PC1"); plt.ylabel("PC2"); plt.tight_layout()
    plt.savefig(ART / "pca_clusters.png", dpi=110); plt.close()
    df["cluster"] = km.labels_
    clusters = []
    for c in range(K):
        sub = df[df.cluster == c]
        clusters.append({"cluster_id": c, "size": int(len(sub)),
                         "means": {f: round(float(sub[f].mean()), 2) for f in CLUSTER_FEATURES},
                         "engaged_rate": round(float(sub[LABEL].mean()), 3)})

    metrics = {
        "model_version": MODEL_VERSION, "chosen_estimator": chosen, "seed": SEED,
        "test_size": 0.25, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__, "eda": eda,
        "selection": {
            "method": f"{CV_FOLDS}-fold stratified cross-validation on the training split only",
            "metric": "f1_mean", "train_rows": int(len(X_tr)), "test_rows": int(len(X_te)),
            "note": "Test split was not used for selection. Test figures are reported once, after selection.",
        },
        "cv_results": cv_results,
        "test_results": test_results,
    }
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (ART / "clusters.json").write_text(json.dumps({
        "k": K, "features": CLUSTER_FEATURES, "silhouette": sil,
        "plot": "backend/ml/artifacts/pca_clusters.png", "plot_url": "/api/v1/clusters/plot",
        "clusters": clusters}, indent=2))
    print(f"model_version={MODEL_VERSION} chosen={chosen} (by {CV_FOLDS}-fold train-only CV F1)")
    for n, r in cv_results.items():
        print(f"  cv {n}: f1={r['f1_mean']}+/-{r['f1_std']} precision={r['precision_mean']} "
              f"recall={r['recall_mean']} accuracy={r['accuracy_mean']}")
    for n, r in test_results.items():
        print(f"  test {n}: precision={r['precision']} recall={r['recall']} f1={r['f1']} "
              f"accuracy={r['accuracy']} cm={r['confusion_matrix']}")
    print(f"kmeans k={K} silhouette={sil}")
    return metrics


if __name__ == "__main__":
    main()
