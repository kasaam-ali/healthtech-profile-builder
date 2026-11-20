// Week 3 review fix (PR #4): fetch helpers for the /ml and /faq pages.
// Every call checks HTTP status, parses defensively, validates the response
// shape, and turns transport, parse and server failures into a typed result
// with a message the page can show. Nothing here throws.

export type Fail = { ok: false; kind: "network" | "unavailable" | "validation" | "server" | "shape"; status?: number; message: string; detail?: string };
export type Result<T> = { ok: true; data: T } | Fail;

export type CvMetric = { f1_mean: number; f1_std: number; precision_mean: number; recall_mean: number; accuracy_mean: number };
export type TestMetric = { precision: number; recall: number; f1: number; accuracy: number; confusion_matrix: number[][] };
export type ModelInfo = { model_version: string; chosen_estimator: string; selection: { method: string }; cv_results: Record<string, CvMetric>; test_results: Record<string, TestMetric>; disclaimer: string };
export type Cluster = { cluster_id: number; size: number; means: Record<string, number>; engaged_rate: number };
export type Clusters = { k: number; silhouette: number; clusters: Cluster[]; plot_url?: string };
export type Prediction = { prediction: string; probability: number; model_version: string; disclaimer: string };
export type FaqAnswer = { abstained: boolean; reason: string | null; answer: string; sources: { id: string; title: string }[]; disclaimer: string };

type Messages = { unavailable: string; validation?: string };
type Guard<T> = (x: unknown) => x is T;

const isObj = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const isStr = (x: unknown): x is string => typeof x === "string";
const allValues = (x: unknown, f: (v: unknown) => boolean) => isObj(x) && Object.values(x).length > 0 && Object.values(x).every(f);

export const isModelInfo: Guard<ModelInfo> = (x): x is ModelInfo =>
  isObj(x) && isStr(x.model_version) && isStr(x.chosen_estimator) && isObj(x.selection) && isStr(x.selection.method) &&
  allValues(x.cv_results, (m) => isObj(m) && isNum(m.f1_mean) && isNum(m.f1_std) && isNum(m.precision_mean) && isNum(m.recall_mean) && isNum(m.accuracy_mean)) &&
  allValues(x.test_results, (m) => isObj(m) && isNum(m.precision) && isNum(m.recall) && isNum(m.f1) && isNum(m.accuracy) && Array.isArray(m.confusion_matrix)) &&
  isStr(x.disclaimer);

export const isClusters: Guard<Clusters> = (x): x is Clusters =>
  isObj(x) && isNum(x.k) && isNum(x.silhouette) && Array.isArray(x.clusters) &&
  x.clusters.every((c) => isObj(c) && isNum(c.cluster_id) && isNum(c.size) && allValues(c.means, isNum));

export const isPrediction: Guard<Prediction> = (x): x is Prediction =>
  isObj(x) && isStr(x.prediction) && isNum(x.probability) && isStr(x.model_version) && isStr(x.disclaimer);

export const isFaqAnswer: Guard<FaqAnswer> = (x): x is FaqAnswer =>
  isObj(x) && typeof x.abstained === "boolean" && isStr(x.answer) && isStr(x.disclaimer) &&
  Array.isArray(x.sources) && x.sources.every((s) => isObj(s) && isStr(s.id) && isStr(s.title));

const NETWORK = "Could not reach the server. Check your connection and try again.";

// FastAPI 422 detail: [{loc: [...], msg: "..."}] -> "field: msg; field: msg"
function validationText(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  return detail.map((d) => {
    const loc = isObj(d) && Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : "input";
    const msg = isObj(d) && isStr(d.msg) ? d.msg : "invalid value";
    return `${loc}: ${msg}`;
  }).join("; ");
}

export async function requestJson<T>(fetchImpl: typeof fetch, url: string, init: RequestInit | undefined, guard: Guard<T>, msg: Messages): Promise<Result<T>> {
  let res: Response;
  try {
    res = await fetchImpl(url, init);
  } catch {
    return { ok: false, kind: "network", message: NETWORK };
  }
  let body: unknown = undefined;
  try {
    const text = await res.text();
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined; // non-JSON body, e.g. a plain-text 500 from a proxy
  }
  if (!res.ok) {
    if (res.status === 422) {
      const v = isObj(body) ? validationText(body.detail) : null;
      return { ok: false, kind: "validation", status: 422, message: msg.validation ?? v ?? "Some inputs are invalid." };
    }
    if (res.status === 503) return { ok: false, kind: "unavailable", status: 503, message: msg.unavailable };
    const detail = isObj(body) && isStr(body.detail) ? body.detail : undefined;
    return { ok: false, kind: "server", status: res.status, message: `The server had a problem (HTTP ${res.status}). Please try again.`, detail };
  }
  if (!guard(body)) return { ok: false, kind: "shape", status: res.status, message: "The server sent an unexpected response. Please try again." };
  return { ok: true, data: body };
}

const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const loadModelInfo = (api: string, f: typeof fetch = fetch) =>
  requestJson(f, `${api}/api/v1/model`, undefined, isModelInfo, { unavailable: "Model information is temporarily unavailable." });

export const loadClusters = (api: string, f: typeof fetch = fetch) =>
  requestJson(f, `${api}/api/v1/clusters`, undefined, isClusters, { unavailable: "Cluster summary is temporarily unavailable." });

export const predict = (api: string, body: unknown, f: typeof fetch = fetch) =>
  requestJson(f, `${api}/api/v1/predict`, json(body), isPrediction, { unavailable: "The prediction model is temporarily unavailable." });

export const askFaq = (api: string, question: string, f: typeof fetch = fetch) =>
  requestJson(f, `${api}/api/v1/faq`, json({ question }), isFaqAnswer, {
    unavailable: "The FAQ service is temporarily unavailable.",
    // Only a 422 means the question itself was rejected.
    validation: "Please enter a question between 3 and 500 characters.",
  });
