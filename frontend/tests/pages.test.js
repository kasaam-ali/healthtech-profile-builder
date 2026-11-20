// PR #4 review item 3: the /ml and /faq pages must survive backend and network failures.
// Renders the real page components in jsdom with a mocked fetch and checks the visible
// state for JSON 503, plain-text 500, rejected fetch, and success. Run with `npm test`.
const test = require("node:test");
const assert = require("node:assert");
const { JSDOM } = require("jsdom");

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000/" });
for (const k of ["window", "document", "navigator", "HTMLElement", "Node", "Event", "MouseEvent"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? dom.window : dom.window[k], configurable: true, writable: true });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const React = require("react");
const { act } = React;
const { createRoot } = require("react-dom/client");
const MlPage = require("../.test-build/app/ml/page.js").default;
const FaqPage = require("../.test-build/app/faq/page.js").default;

const unhandled = [];
process.on("unhandledRejection", (e) => unhandled.push(e));

// ---------- fixtures ----------
const DISC = "Fictional educational demo built on synthetic data. Not medical advice, diagnosis, triage, or treatment.";
const MODEL = {
  model_version: "engagement-v1.1.0", chosen_estimator: "logistic_regression",
  selection: { method: "5-fold stratified cross-validation on the training split only" },
  cv_results: { logistic_regression: { f1_mean: 0.7491, f1_std: 0.0194, precision_mean: 0.7489, recall_mean: 0.7497, accuracy_mean: 0.7487 } },
  test_results: { logistic_regression: { precision: 0.7437, recall: 0.708, f1: 0.7254, accuracy: 0.732, confusion_matrix: [[189, 61], [73, 177]] } },
  disclaimer: DISC,
};
const CLUSTERS = { k: 1, silhouette: 0.2823, plot_url: "/api/v1/clusters/plot", disclaimer: DISC,
  clusters: [{ cluster_id: 0, size: 807, means: { sessions_last_30d: 5.97, avg_session_minutes: 11.8, days_since_signup: 239.08 }, engaged_rate: 0.559 }] };
const PRED = { prediction: "likely_engaged", probability: 0.61, model_version: "engagement-v1.1.0", estimator: "logistic_regression", disclaimer: DISC };
const FAQ = { abstained: false, reason: null, answer: "Each member can store up to 5 emergency contacts.", sources: [{ id: "emergency-contacts", title: "Emergency contacts limit", score: 4 }], disclaimer: DISC };

const ok = (body) => () => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
const json503 = () => () => Promise.resolve(new Response(JSON.stringify({ detail: "The prediction model is temporarily unavailable. Please try again later." }), { status: 503, headers: { "Content-Type": "application/json" } }));
const text500 = () => () => Promise.resolve(new Response("Internal Server Error", { status: 500, headers: { "Content-Type": "text/plain" } }));
const rejected = () => () => Promise.reject(new TypeError("Failed to fetch"));
const json422 = (detail) => () => Promise.resolve(new Response(JSON.stringify({ detail }), { status: 422, headers: { "Content-Type": "application/json" } }));

// routes: { "/api/v1/model": handler, ... }; handlers can be swapped mid-test for retry.
function mockFetch(routes) {
  const calls = [];
  globalThis.fetch = (url, init) => {
    const path = new URL(url).pathname;
    calls.push(path);
    const h = routes[path];
    if (!h) return Promise.reject(new Error(`unmocked ${path}`));
    return h(init);
  };
  return calls;
}

async function render(Component) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(React.createElement(Component)); });
  await flush();
  return { container, unmount: () => act(() => root.unmount()) };
}

async function flush() {
  for (let i = 0; i < 5; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

const text = (el) => el.textContent.replace(/\s+/g, " ");
const byTestId = (c, id) => c.querySelector(`[data-testid="${id}"]`);
const button = (c, label) => [...c.querySelectorAll("button")].find((b) => b.textContent.trim() === label);
async function click(el) { await act(async () => { el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })); }); await flush(); }
async function submit(c) { await act(async () => { c.querySelector("form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })); }); await flush(); }

test.afterEach(() => { document.body.innerHTML = ""; assert.deepStrictEqual(unhandled, [], "no unhandled promise rejections"); });

// ---------- /ml ----------
test("ml: success renders tables, cluster list, plot image with alt text, and the limitation", async () => {
  mockFetch({ "/api/v1/model": ok(MODEL), "/api/v1/clusters": ok(CLUSTERS) });
  const { container } = await render(MlPage);
  assert.match(text(container), /engagement-v1\.1\.0/);
  assert.match(text(container), /Final held-out test report/);
  const img = container.querySelector("img");
  assert.ok(img, "plot rendered as an image, not a file path");
  assert.equal(img.getAttribute("src"), "http://localhost:8000/api/v1/clusters/plot");
  assert.match(img.getAttribute("alt"), /PCA components.*K-Means/);
  assert.doesNotMatch(text(container), /backend\/ml\/artifacts/);
  assert.match(text(container), /Limitation:.*exploratory/);
});

test("ml: JSON 503 on model keeps clusters visible, shows a model error, and retry recovers", async () => {
  const routes = { "/api/v1/model": json503(), "/api/v1/clusters": ok(CLUSTERS) };
  mockFetch(routes);
  const { container } = await render(MlPage);
  assert.match(text(byTestId(container, "model-error")), /Model information is temporarily unavailable/);
  assert.equal(byTestId(container, "clusters-error"), null);
  assert.match(text(container), /Cluster 0: 807 members/);
  routes["/api/v1/model"] = ok(MODEL);
  await click(button(container, "Retry model info"));
  assert.equal(byTestId(container, "model-error"), null);
  assert.match(text(container), /Selection evidence/);
});

test("ml: plain-text 500 on clusters shows a clusters error and keeps the model table", async () => {
  const routes = { "/api/v1/model": ok(MODEL), "/api/v1/clusters": text500() };
  mockFetch(routes);
  const { container } = await render(MlPage);
  assert.match(text(byTestId(container, "clusters-error")), /HTTP 500/);
  assert.equal(byTestId(container, "model-error"), null);
  assert.match(text(container), /Selection evidence/);
  routes["/api/v1/clusters"] = ok(CLUSTERS);
  await click(button(container, "Retry clusters"));
  assert.equal(byTestId(container, "clusters-error"), null);
  assert.ok(container.querySelector("img"));
});

test("ml: rejected fetch on both shows two separate network errors without crashing", async () => {
  mockFetch({ "/api/v1/model": rejected(), "/api/v1/clusters": rejected() });
  const { container } = await render(MlPage);
  assert.match(text(byTestId(container, "model-error")), /Could not reach the server/);
  assert.match(text(byTestId(container, "clusters-error")), /Could not reach the server/);
});

test("ml: a 200 with an error-shaped body is rejected instead of dereferenced", async () => {
  mockFetch({ "/api/v1/model": ok({ detail: "oops" }), "/api/v1/clusters": ok({ clusters: "nope" }) });
  const { container } = await render(MlPage);
  assert.match(text(byTestId(container, "model-error")), /unexpected response/);
  assert.match(text(byTestId(container, "clusters-error")), /unexpected response/);
});

for (const [name, handler, expected] of [
  ["JSON 503", json503(), /prediction model is temporarily unavailable/],
  ["plain-text 500", text500(), /HTTP 500/],
  ["rejected fetch", rejected(), /Could not reach the server/],
  ["422 validation", json422([{ loc: ["body", "age"], msg: "Input should be greater than or equal to 18" }]), /age: Input should be greater than or equal to 18/],
]) {
  test(`ml: predict ${name} shows a predict error and the page keeps working`, async () => {
    const routes = { "/api/v1/model": ok(MODEL), "/api/v1/clusters": ok(CLUSTERS), "/api/v1/predict": handler };
    mockFetch(routes);
    const { container } = await render(MlPage);
    await submit(container);
    assert.match(text(byTestId(container, "predict-error")), expected);
    assert.equal(byTestId(container, "model-error"), null);
    routes["/api/v1/predict"] = ok(PRED);
    await click(button(container, "Retry prediction"));
    assert.equal(byTestId(container, "predict-error"), null);
    assert.match(text(container), /Result: likely_engaged/);
  });
}

test("ml: predict button is disabled while the request is pending", async () => {
  let release;
  mockFetch({ "/api/v1/model": ok(MODEL), "/api/v1/clusters": ok(CLUSTERS),
    "/api/v1/predict": () => new Promise((r) => { release = () => r(new Response(JSON.stringify(PRED), { status: 200 })); }) });
  const { container } = await render(MlPage);
  await submit(container);
  const b = button(container, "Predicting...");
  assert.ok(b && b.disabled);
  release(); await flush();
  assert.ok(button(container, "Predict engagement"));
  assert.match(text(container), /Result: likely_engaged/);
});

// ---------- /faq ----------
test("faq: success shows the answer and its source", async () => {
  mockFetch({ "/api/v1/faq": ok(FAQ) });
  const { container } = await render(FaqPage);
  await submit(container);
  assert.match(text(container), /up to 5 emergency contacts/);
  assert.match(text(container), /Source: Emergency contacts limit/);
});

test("faq: only a 422 is reported as a question-length problem, with no retry", async () => {
  mockFetch({ "/api/v1/faq": json422([{ loc: ["body", "question"], msg: "String should have at least 3 characters" }]) });
  const { container } = await render(FaqPage);
  await submit(container);
  assert.match(text(byTestId(container, "faq-error")), /between 3 and 500 characters/);
  assert.equal(button(container, "Retry"), undefined);
});

for (const [name, handler, expected] of [
  ["JSON 503", json503(), /FAQ service is temporarily unavailable/],
  ["plain-text 500", text500(), /HTTP 500/],
  ["rejected fetch", rejected(), /Could not reach the server/],
]) {
  test(`faq: ${name} shows a specific error (not question length) and retry recovers`, async () => {
    const routes = { "/api/v1/faq": handler };
    mockFetch(routes);
    const { container } = await render(FaqPage);
    await submit(container);
    const err = text(byTestId(container, "faq-error"));
    assert.match(err, expected);
    assert.doesNotMatch(err, /between 3 and 500/);
    routes["/api/v1/faq"] = ok(FAQ);
    await click(button(container, "Retry"));
    assert.equal(byTestId(container, "faq-error"), null);
    assert.match(text(container), /up to 5 emergency contacts/);
  });
}

test("faq: Ask is disabled while pending", async () => {
  let release;
  mockFetch({ "/api/v1/faq": () => new Promise((r) => { release = () => r(new Response(JSON.stringify(FAQ), { status: 200 })); }) });
  const { container } = await render(FaqPage);
  await submit(container);
  assert.ok(button(container, "Asking...").disabled);
  release(); await flush();
  assert.ok(button(container, "Ask"));
});
