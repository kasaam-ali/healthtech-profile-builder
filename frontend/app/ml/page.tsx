"use client";
import { FormEvent, useEffect, useState } from "react";
import { API } from "../../lib/api";

type CvMetric = { f1_mean: number; f1_std: number; precision_mean: number; recall_mean: number; accuracy_mean: number };
type TestMetric = { precision: number; recall: number; f1: number; accuracy: number; confusion_matrix: number[][] };
type ModelInfo = { model_version: string; chosen_estimator: string; selection: { method: string }; cv_results: Record<string, CvMetric>; test_results: Record<string, TestMetric>; disclaimer: string };
type Cluster = { cluster_id: number; size: number; means: Record<string, number>; engaged_rate: number };
type Clusters = { k: number; silhouette: number; clusters: Cluster[] };
type Prediction = { prediction: string; probability: number; model_version: string; disclaimer: string };

const initial = { age: 34, sessions_last_30d: 8, avg_session_minutes: 15, days_since_signup: 200, reminders_opt_in: true, preferred_channel: "app" };

export default function MlPage() {
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [clusters, setClusters] = useState<Clusters | null>(null);
  const [form, setForm] = useState(initial);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/api/v1/model`).then((r) => r.json()).then(setInfo).catch(() => setError("Backend not reachable."));
    fetch(`${API}/api/v1/clusters`).then((r) => r.json()).then(setClusters).catch(() => {});
  }, []);

  const num = (k: keyof typeof initial) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });

  async function submit(e: FormEvent) {
    e.preventDefault(); setError(""); setPred(null);
    const res = await fetch(`${API}/api/v1/predict`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
    const data = await res.json();
    if (!res.ok) { setError(Array.isArray(data.detail) ? data.detail.map((d: { msg: string }) => d.msg).join("; ") : "Request failed"); return; }
    setPred(data);
  }

  return (
    <main>
      <h1>Educational ML demo</h1>
      <p><strong>Fictional synthetic data only. Not medical advice, diagnosis, triage, or treatment.</strong></p>

      <h2>Model comparison</h2>
      {info && (
        <>
          <p>Version <code>{info.model_version}</code>, chosen by {info.selection.method} (F1): {info.chosen_estimator}</p>
          <h3>Selection evidence (cross-validation on the training split only)</h3>
          <table><thead><tr><th>Model</th><th>CV F1 (mean +/- std)</th><th>CV precision</th><th>CV recall</th><th>CV accuracy</th></tr></thead>
            <tbody>{Object.entries(info.cv_results).map(([n, m]) => (
              <tr key={n}><td>{n}</td><td>{m.f1_mean} +/- {m.f1_std}</td><td>{m.precision_mean}</td><td>{m.recall_mean}</td><td>{m.accuracy_mean}</td></tr>
            ))}</tbody></table>
          <h3>Final held-out test report (not used for selection)</h3>
          <table><thead><tr><th>Model</th><th>Precision</th><th>Recall</th><th>F1</th><th>Accuracy</th><th>Confusion [[TN, FP], [FN, TP]]</th></tr></thead>
            <tbody>{Object.entries(info.test_results).map(([n, m]) => (
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
        <button type="submit">Predict engagement</button>
      </form>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      {pred && (
        <div>
          <p>Result: <strong>{pred.prediction}</strong> (probability {pred.probability}, model {pred.model_version})</p>
          <p><em>{pred.disclaimer}</em></p>
        </div>
      )}

      <h2>Engagement clusters (K-Means)</h2>
      {clusters && (
        <>
          <p>k = {clusters.k}, silhouette = {clusters.silhouette} (modest separation; descriptive only).</p>
          <ul>{clusters.clusters.map((c) => (
            <li key={c.cluster_id}>Cluster {c.cluster_id}: {c.size} members, avg sessions {c.means.sessions_last_30d}, avg minutes {c.means.avg_session_minutes}, avg days since signup {c.means.days_since_signup}</li>
          ))}</ul>
          <p>PCA plot: <code>backend/ml/artifacts/pca_clusters.png</code></p>
        </>
      )}
    </main>
  );
}
