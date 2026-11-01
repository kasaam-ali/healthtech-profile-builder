"""Recreate Week 3 ML artifacts end to end.

Usage (from backend/):  python -m scripts.train_ml

Steps: generate synthetic data, EDA summary, reproducible stratified split,
train Logistic Regression and Random Forest inside the same preprocessing
pipeline (fit on train only, so no leakage), compare metrics, save the best
pipeline with a version tag, then run K-Means + PCA on non-sensitive
engagement attributes and save a plot.
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
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (confusion_matrix, f1_score, precision_score,  # noqa: E402
                             recall_score, silhouette_score)
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from ml.dataset import (BOOLEAN, CATEGORICAL, FEATURES, LABEL, NUMERIC, SEED,  # noqa: E402
                        generate, write_csv)

MODEL_VERSION = "engagement-v1.0.0"
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
    }
    results, pipes = {}, {}
    for name, est in candidates.items():
        pipe = Pipeline([("prep", preprocessor()), ("clf", est)]).fit(X_tr, y_tr)
        pred = pipe.predict(X_te)
        results[name] = {
            "precision": round(float(precision_score(y_te, pred)), 4),
            "recall": round(float(recall_score(y_te, pred)), 4),
            "f1": round(float(f1_score(y_te, pred)), 4),
            "confusion_matrix": confusion_matrix(y_te, pred).tolist(),
        }
        pipes[name] = pipe
    chosen = max(results, key=lambda n: results[n]["f1"])
    joblib.dump({"pipeline": pipes[chosen], "model_version": MODEL_VERSION,
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
        "sklearn_version": sklearn.__version__, "eda": eda, "results": results,
    }
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (ART / "clusters.json").write_text(json.dumps({
        "k": K, "features": CLUSTER_FEATURES, "silhouette": sil,
        "plot": "backend/ml/artifacts/pca_clusters.png", "clusters": clusters}, indent=2))
    print(f"model_version={MODEL_VERSION} chosen={chosen}")
    for n, r in results.items():
        print(f"  {n}: precision={r['precision']} recall={r['recall']} f1={r['f1']} cm={r['confusion_matrix']}")
    print(f"kmeans k={K} silhouette={sil}")
    return metrics


if __name__ == "__main__":
    main()
