# Week 3 clustering

- Features (non-sensitive, behaviour only): `sessions_last_30d`, `avg_session_minutes`, `days_since_signup`, standardized. Age and channel are deliberately excluded.
- Algorithm: K-Means, k=3, `n_init=10`, `random_state=42`.
- **Silhouette score: 0.2823** (weak to moderate separation; clusters overlap).
- PCA 2D plot: `backend/ml/artifacts/pca_clusters.png`, served as `image/png` by `GET /api/v1/clusters/plot` and shown on `/ml` with alt text and a caption (503 if the file is missing or not a PNG).
- Summary served by `GET /api/v1/clusters` from `backend/ml/artifacts/clusters.json` (size, feature means, engaged rate per cluster).

## Limitations
- k=3 was picked for readability, not by an exhaustive elbow/silhouette search.
- The data is synthetic and roughly unimodal, so clusters are partitions more than natural groups.
- Clusters are descriptive only and must not be used to make decisions about any person.
