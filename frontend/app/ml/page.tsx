"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { API } from "../../lib/api";
import { Clusters, ModelInfo, Prediction, loadClusters, loadModelInfo, predict } from "../../lib/mlClient";

// Each section keeps its own state, so a model failure never hides the clusters and vice versa.
type Section<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; message: string };

const initial = { age: 34, sessions_last_30d: 8, avg_session_minutes: 15, days_since_signup: 200, reminders_opt_in: true, preferred_channel: "app" };

const errStyle = { color: "crimson" } as const;

export default function MlPage() {
  const [info, setInfo] = useState<Section<ModelInfo>>({ status: "loading" });
  const [clusters, setClusters] = useState<Section<Clusters>>({ status: "loading" });
  const [form, setForm] = useState(initial);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [predError, setPredError] = useState("");
  const [pending, setPending] = useState(false);
  const [plotFailed, setPlotFailed] = useState(false);

  const fetchInfo = useCallback(async () => {
    setInfo({ status: "loading" });
    const r = await loadModelInfo(API);
    setInfo(r.ok ? { status: "ready", data: r.data } : { status: "error", message: r.message });
  }, []);
  const fetchClusters = useCallback(async () => {
    setClusters({ status: "loading" });
    setPlotFailed(false);
    const r = await loadClusters(API);
    setClusters(r.ok ? { status: "ready", data: r.data } : { status: "error", message: r.message });
  }, []);

  useEffect(() => { void fetchInfo(); void fetchClusters(); }, [fetchInfo, fetchClusters]);

  const num = (k: keyof typeof initial) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });

  function submit(e: FormEvent) { e.preventDefault(); void runPredict(); }

  async function runPredict() {
    if (pending) return;
    setPredError(""); setPred(null); setPending(true);
    const r = await predict(API, form);
    setPending(false);
    if (r.ok) setPred(r.data); else setPredError(r.message);
  }

  return (
    <main>
      <h1>Educational ML demo</h1>
      <p><strong>Fictional synthetic data only. Not medical advice, diagnosis, triage, or treatment.</strong></p>

      <h2>Model comparison</h2>
      {info.status === "loading" && <p aria-live="polite">Loading model information...</p>}
      {info.status === "error" && (
        <div role="alert" data-testid="model-error">
          <p style={errStyle}>{info.message}</p>
          <button type="button" onClick={() => void fetchInfo()}>Retry model info</button>
        </div>
      )}
      {info.status === "ready" && (
        <>
          <p>Version <code>{info.data.model_version}</code>, chosen by {info.data.selection.method} (F1): {info.data.chosen_estimator}</p>
          <h3>Selection evidence (cross-validation on the training split only)</h3>
          <table><thead><tr><th>Model</th><th>CV F1 (mean +/- std)</th><th>CV precision</th><th>CV recall</th><th>CV accuracy</th></tr></thead>
            <tbody>{Object.entries(info.data.cv_results).map(([n, m]) => (
              <tr key={n}><td>{n}</td><td>{m.f1_mean} +/- {m.f1_std}</td><td>{m.precision_mean}</td><td>{m.recall_mean}</td><td>{m.accuracy_mean}</td></tr>
            ))}</tbody></table>
          <h3>Final held-out test report (not used for selection)</h3>
          <table><thead><tr><th>Model</th><th>Precision</th><th>Recall</th><th>F1</th><th>Accuracy</th><th>Confusion [[TN, FP], [FN, TP]]</th></tr></thead>
            <tbody>{Object.entries(info.data.test_results).map(([n, m]) => (
              <tr key={n}><td>{n}</td><td>{m.precision}</td><td>{m.recall}</td><td>{m.f1}</td><td>{m.accuracy}</td><td>{JSON.stringify(m.confusion_matrix)}</td></tr>
            ))}</tbody></table>
        </>
      )}

      <h2>Try a prediction (synthetic member)</h2>
      <form onSubmit={submit}>
        <label>Age <input type="number" min={18} max={100} value={form.age} onChange={num("age")} /></label>
        <label>Sessions (30d) <input type="number" min={0} max={60} value={form.sessions_last_30d} onChange={num("sessions_last_30d")} /></label>
        <label>Avg session minutes <input type="number" min={0} max={240} step="0.1" value={form.avg_session_minutes} onChange={num("avg_session_minutes")} /></label>
        <label>Days since signup <input type="number" min={0} max={3650} value={form.days_since_signup} onChange={num("days_since_signup")} /></label>
        <label>Reminders <input type="checkbox" checked={form.reminders_opt_in} onChange={(e) => setForm({ ...form, reminders_opt_in: e.target.checked })} /></label>
        <label>Channel <select value={form.preferred_channel} onChange={(e) => setForm({ ...form, preferred_channel: e.target.value })}>
          <option value="email">email</option><option value="sms">sms</option><option value="app">app</option></select></label>
        <button type="submit" disabled={pending}>{pending ? "Predicting..." : "Predict engagement"}</button>
      </form>
      {predError && (
        <div role="alert" data-testid="predict-error">
          <p style={errStyle}>{predError}</p>
          <button type="button" onClick={() => void runPredict()} disabled={pending}>Retry prediction</button>
        </div>
      )}
      {pred && (
        <div>
          <p>Result: <strong>{pred.prediction}</strong> (probability {pred.probability}, model {pred.model_version})</p>
          <p><em>{pred.disclaimer}</em></p>
        </div>
      )}

      <h2>Engagement clusters (K-Means)</h2>
      <p><strong>Limitation:</strong> exploratory clustering on synthetic data. Separation is modest, clusters overlap, and they are descriptive only. They must not be used to make decisions about anyone.</p>
      {clusters.status === "loading" && <p aria-live="polite">Loading cluster summary...</p>}
      {clusters.status === "error" && (
        <div role="alert" data-testid="clusters-error">
          <p style={errStyle}>{clusters.message}</p>
          <button type="button" onClick={() => void fetchClusters()}>Retry clusters</button>
        </div>
      )}
      {clusters.status === "ready" && (
        <>
          <p>k = {clusters.data.k}, silhouette = {clusters.data.silhouette} (modest separation; descriptive only).</p>
          <ul>{clusters.data.clusters.map((c) => (
            <li key={c.cluster_id}>Cluster {c.cluster_id}: {c.size} members, avg sessions {c.means.sessions_last_30d}, avg minutes {c.means.avg_session_minutes}, avg days since signup {c.means.days_since_signup}</li>
          ))}</ul>
          <figure style={{ margin: 0 }}>
            {plotFailed ? (
              <p style={errStyle}>The cluster plot could not be loaded.</p>
            ) : (
              <img
                src={`${API}${clusters.data.plot_url ?? "/api/v1/clusters/plot"}`}
                alt={`Scatter plot of synthetic members projected onto two PCA components, coloured by K-Means cluster (k = ${clusters.data.k}). The clusters overlap, matching the modest silhouette score of ${clusters.data.silhouette}.`}
                style={{ maxWidth: "100%", height: "auto" }}
                onError={() => setPlotFailed(true)}
              />
            )}
            <figcaption>PCA 2D projection of standardized sessions, session minutes and days since signup. Axes are principal components, not original features.</figcaption>
          </figure>
        </>
      )}
    </main>
  );
}
