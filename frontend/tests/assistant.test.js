// Week 4: the /assistant page (cited RAG FAQ, availability tool, confirmed hold) must
// survive backend and network failures the same way /ml and /faq do after the PR #4
// review. Renders the real page in jsdom with a mocked fetch. Run with `npm test`.
const test = require("node:test");
const assert = require("node:assert");
const { JSDOM } = require("jsdom");

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000/" });
for (const k of ["window", "document", "navigator", "HTMLElement", "Node", "Event", "MouseEvent", "sessionStorage"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? dom.window : dom.window[k], configurable: true, writable: true });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const React = require("react");
const { act } = React;
const { createRoot } = require("react-dom/client");
const AssistantPage = require("../.test-build/app/assistant/page.js").default;

const unhandled = [];
process.on("unhandledRejection", (e) => unhandled.push(e));

const DISC = "Fictional demo clinic. Answers come only from approved fictional policy documents. Not medical advice, diagnosis, triage, or treatment.";
const ANSWER = { abstained: false, reason: null, answer: "A hold lasts 24 hours.", disclaimer: DISC,
  citations: [{ doc_id: "DOC-003", title: "Appointments", chunk_id: "DOC-003#0", score: 0.41 }] };
const ABSTAIN = { abstained: true, reason: "medical", answer: "I can only answer clinic policy questions.", citations: [], disclaimer: DISC };
const SLOTS = { tool: "check_appointment_availability", disclaimer: DISC,
  slots: [{ slot_id: "S-2026-11-20-1000", date: "2026-11-20", start: "10:00", coach: "Coach Amina (fictional)", status: "open" }] };
const HOLD = { tool: "request_appointment_hold", hold_id: 1, slot_id: "S-2026-11-20-1000", status: "held", note: "Hold is a request only; staff confirm within 24 hours (fictional)." };

const res = (status, body, type = "application/json") => () => Promise.resolve(new Response(typeof body === "string" ? body : JSON.stringify(body), { status, headers: { "Content-Type": type } }));
const ok = (b) => res(200, b);
const json503 = (detail = "Document retrieval is temporarily unavailable. Please try again.") => res(503, { detail });
const text500 = () => res(500, "Internal Server Error", "text/plain");
const rejected = () => () => Promise.reject(new TypeError("Failed to fetch"));

const FAQ = "/api/v2/faq", AVAIL = "/api/v2/tools/check_appointment_availability", HOLDP = "/api/v2/tools/request_appointment_hold";

function mockFetch(routes) {
  const calls = [];
  globalThis.fetch = (url, init) => {
    const path = new URL(url).pathname;
    calls.push({ path, init });
    const h = routes[path];
    return h ? h(init) : Promise.reject(new Error(`unmocked ${path}`));
  };
  return calls;
}

async function flush() { for (let i = 0; i < 5; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); }
async function render() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(React.createElement(AssistantPage)); });
  await flush();
  return container;
}
const text = (el) => el.textContent.replace(/\s+/g, " ");
const byTestId = (c, id) => c.querySelector(`[data-testid="${id}"]`);
const button = (c, label) => [...c.querySelectorAll("button")].find((b) => b.textContent.trim() === label);
async function click(el) { await act(async () => { el.click(); }); await flush(); }
async function submit(c, id) { await act(async () => { byTestId(c, id).dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })); }); await flush(); }
async function pickSlotAndConfirm(c) {
  await click(c.querySelector('input[type="radio"]'));
  await click(c.querySelector('input[type="checkbox"]'));
}

test.beforeEach(() => { sessionStorage.clear(); });
test.afterEach(() => { document.body.innerHTML = ""; assert.deepStrictEqual(unhandled, [], "no unhandled promise rejections"); });

test("assistant: cited answer renders doc id, title and chunk id", async () => {
  mockFetch({ [FAQ]: ok(ANSWER) });
  const c = await render();
  await submit(c, "faq-form");
  assert.match(text(c), /A hold lasts 24 hours/);
  assert.match(text(c), /DOC-003: Appointments \(DOC-003#0\)/);
});

test("assistant: abstention is labelled and shows no citations", async () => {
  mockFetch({ [FAQ]: ok(ABSTAIN) });
  const c = await render();
  await submit(c, "faq-form");
  assert.match(text(byTestId(c, "faq-answer")), /Not answered: I can only answer clinic policy questions/);
  assert.equal(byTestId(c, "faq-answer").querySelector("li"), null);
});

for (const [name, handler, expected] of [
  ["JSON 503", json503(), /Document retrieval is temporarily unavailable/],
  ["plain-text 500", text500(), /HTTP 500/],
  ["rejected fetch", rejected(), /Could not reach the server/],
  ["error-shaped 200", ok({ detail: "oops" }), /unexpected response/],
]) {
  test(`assistant: FAQ ${name} shows a specific error and retry recovers`, async () => {
    const routes = { [FAQ]: handler };
    mockFetch(routes);
    const c = await render();
    await submit(c, "faq-form");
    const err = text(byTestId(c, "faq-error"));
    assert.match(err, expected);
    assert.doesNotMatch(err, /between 3 and 500/);
    routes[FAQ] = ok(ANSWER);
    await click(button(c, "Retry question"));
    assert.equal(byTestId(c, "faq-error"), null);
    assert.match(text(c), /A hold lasts 24 hours/);
  });
}

test("assistant: FAQ 422 is a question-length problem with no retry", async () => {
  mockFetch({ [FAQ]: res(422, { detail: [{ loc: ["body", "question"], msg: "too short" }] }) });
  const c = await render();
  await submit(c, "faq-form");
  assert.match(text(byTestId(c, "faq-error")), /between 3 and 500 characters/);
  assert.equal(button(c, "Retry question"), undefined);
});

test("assistant: Ask is disabled while pending", async () => {
  let release;
  mockFetch({ [FAQ]: () => new Promise((r) => { release = () => r(new Response(JSON.stringify(ANSWER), { status: 200 })); }) });
  const c = await render();
  await submit(c, "faq-form");
  assert.ok(button(c, "Asking...").disabled);
  release(); await flush();
  assert.ok(button(c, "Ask"));
});

for (const [name, handler, expected] of [
  ["plain-text 500", text500(), /HTTP 500/],
  ["rejected fetch", rejected(), /Could not reach the server/],
  ["error-shaped 200", ok({ slots: "nope" }), /unexpected response/],
]) {
  test(`assistant: availability ${name} shows a slots error, FAQ still works, retry recovers`, async () => {
    const routes = { [AVAIL]: handler, [FAQ]: ok(ANSWER) };
    mockFetch(routes);
    const c = await render();
    await submit(c, "slots-form");
    assert.match(text(byTestId(c, "slots-error")), expected);
    await submit(c, "faq-form");
    assert.match(text(c), /A hold lasts 24 hours/);
    routes[AVAIL] = ok(SLOTS);
    await click(button(c, "Retry availability"));
    assert.equal(byTestId(c, "slots-error"), null);
    assert.match(text(c), /2026-11-20 10:00 with Coach Amina/);
  });
}

test("assistant: hold button stays disabled until a slot is picked and confirmed", async () => {
  sessionStorage.setItem("access_token", "t");
  mockFetch({ [AVAIL]: ok(SLOTS) });
  const c = await render();
  await submit(c, "slots-form");
  assert.ok(button(c, "Request hold").disabled);
  await click(c.querySelector('input[type="radio"]'));
  assert.ok(button(c, "Request hold").disabled);
  await click(c.querySelector('input[type="checkbox"]'));
  assert.equal(button(c, "Request hold").disabled, false);
});

test("assistant: confirmed hold sends the bearer token and human_confirmed=true", async () => {
  sessionStorage.setItem("access_token", "member-token");
  const calls = mockFetch({ [AVAIL]: ok(SLOTS), [HOLDP]: res(201, HOLD) });
  const c = await render();
  await submit(c, "slots-form");
  await pickSlotAndConfirm(c);
  await click(button(c, "Request hold"));
  const call = calls.find((x) => x.path === HOLDP);
  assert.equal(call.init.headers.Authorization, "Bearer member-token");
  assert.deepStrictEqual(JSON.parse(call.init.body), { slot_id: "S-2026-11-20-1000", human_confirmed: true });
  assert.match(text(byTestId(c, "hold-ok")), /Hold requested for S-2026-11-20-1000/);
});

test("assistant: hold without login is refused client-side and nothing is sent", async () => {
  const calls = mockFetch({ [AVAIL]: ok(SLOTS) });
  const c = await render();
  await submit(c, "slots-form");
  await pickSlotAndConfirm(c);
  await click(button(c, "Request hold"));
  assert.match(text(byTestId(c, "hold-error")), /Please log in/);
  assert.equal(calls.filter((x) => x.path === HOLDP).length, 0);
});

for (const [name, handler, expected, retry] of [
  ["503 provider timeout", json503("Calendar provider unavailable. No hold was created."), /Calendar provider unavailable\. No hold was created/, true],
  ["409 conflict", res(409, { detail: "Slot is already held." }), /Slot is already held/, false],
  ["401 expired session", res(401, { detail: "Invalid token" }), /session expired/, false],
  ["plain-text 500", text500(), /HTTP 500/, true],
  ["rejected fetch", rejected(), /Could not reach the server/, true],
]) {
  test(`assistant: hold ${name} shows a hold error without crashing`, async () => {
    sessionStorage.setItem("access_token", "member-token");
    const routes = { [AVAIL]: ok(SLOTS), [HOLDP]: handler };
    mockFetch(routes);
    const c = await render();
    await submit(c, "slots-form");
    await pickSlotAndConfirm(c);
    await click(button(c, "Request hold"));
    assert.match(text(byTestId(c, "hold-error")), expected);
    assert.equal(!!button(c, "Retry hold"), retry);
    if (name.startsWith("401")) assert.equal(sessionStorage.getItem("access_token"), null);
    if (retry) {
      routes[HOLDP] = res(201, HOLD);
      await click(button(c, "Retry hold"));
      assert.equal(byTestId(c, "hold-error"), null);
      assert.match(text(byTestId(c, "hold-ok")), /Hold requested/);
    }
  });
}
