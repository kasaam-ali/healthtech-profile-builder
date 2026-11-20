"use client";
import { FormEvent, useState } from "react";
import { API, tokenStore } from "../../lib/api";
import { RagAnswer, Slot, askRag, checkAvailability, releaseHold, requestHold } from "../../lib/assistantClient";

type Err = { message: string; retryable: boolean } | null;

export default function AssistantPage() {
  const [q, setQ] = useState("");
  const [a, setA] = useState<RagAnswer | null>(null);
  const [faqErr, setFaqErr] = useState<Err>(null);
  const [asking, setAsking] = useState(false);

  const [date, setDate] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slotsErr, setSlotsErr] = useState<Err>(null);
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState(false);

  const [picked, setPicked] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [holdMsg, setHoldMsg] = useState("");
  const [holdErr, setHoldErr] = useState<Err>(null);
  const [holding, setHolding] = useState(false);
  const [activeHold, setActiveHold] = useState<{ hold_id: number; slot_id: string } | null>(null);
  const [releasing, setReleasing] = useState(false);

  async function sendQuestion() {
    if (asking) return;
    setFaqErr(null); setA(null); setAsking(true);
    const r = await askRag(API, q, tokenStore.get());
    setAsking(false);
    if (r.ok) setA(r.data);
    else setFaqErr({ message: r.message, retryable: r.kind !== "validation" });
  }

  async function sendLookup() {
    if (checking) return;
    setSlotsErr(null); setHoldMsg(""); setHoldErr(null); setPicked(""); setConfirmed(false); setChecking(true);
    const r = await checkAvailability(API, date, tokenStore.get());
    setChecking(false);
    if (r.ok) { setSlots(r.data.slots); setChecked(true); }
    else { setSlots([]); setChecked(false); setSlotsErr({ message: r.message, retryable: r.kind !== "validation" }); }
  }

  async function sendHold() {
    if (holding || !picked || !confirmed) return;
    setHoldErr(null); setHoldMsg(""); setHolding(true);
    const r = await requestHold(API, picked, confirmed, tokenStore.get());
    setHolding(false);
    if (r.ok) {
      setHoldMsg(`Hold requested for ${r.data.slot_id}. ${r.data.note}`);
      setActiveHold({ hold_id: r.data.hold_id, slot_id: r.data.slot_id });
      setSlots(slots.filter((s) => s.slot_id !== picked)); setPicked(""); setConfirmed(false);
      return;
    }
    if (r.status === 401) tokenStore.clear();
    setHoldErr({ message: r.message, retryable: r.kind !== "validation" });
  }

  async function sendRelease() {
    if (releasing || !activeHold) return;
    setHoldErr(null); setReleasing(true);
    const r = await releaseHold(API, activeHold.hold_id, tokenStore.get());
    setReleasing(false);
    if (r.ok) {
      setHoldMsg(`Hold on ${activeHold.slot_id} was released. The slot is available again.`);
      setActiveHold(null);
      return;
    }
    if (r.status === 401) tokenStore.clear();
    setHoldErr({ message: r.message, retryable: r.kind !== "validation" });
  }

  const ask = (e: FormEvent) => { e.preventDefault(); void sendQuestion(); };
  const lookup = (e: FormEvent) => { e.preventDefault(); void sendLookup(); };

  return (
    <main>
      <h1>Clinic assistant</h1>
      <p>Answers cite approved fictional clinic documents. Medical questions are not answered.</p>
      <form onSubmit={ask} data-testid="faq-form">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. How long does a hold last?" size={40} aria-label="Question" />
        <button type="submit" disabled={asking}>{asking ? "Asking..." : "Ask"}</button>
      </form>
      {faqErr && (
        <div role="alert" data-testid="faq-error">
          <p style={{ color: "crimson" }}>{faqErr.message}</p>
          {faqErr.retryable && <button type="button" onClick={() => void sendQuestion()} disabled={asking}>Retry question</button>}
        </div>
      )}
      {a && (
        <section data-testid="faq-answer">
          <p>{a.abstained ? "Not answered: " : ""}{a.answer}</p>
          {a.citations.length > 0 && (
            <ul>{a.citations.map((c) => <li key={c.chunk_id}>{c.doc_id}: {c.title} ({c.chunk_id})</li>)}</ul>
          )}
          <p><em>{a.disclaimer}</em></p>
        </section>
      )}

      <h2>Appointment availability</h2>
      <form onSubmit={lookup} data-testid="slots-form">
        <input value={date} onChange={(e) => setDate(e.target.value)} placeholder="YYYY-MM-DD (optional)" aria-label="Date" />
        <button type="submit" disabled={checking}>{checking ? "Checking..." : "Check"}</button>
      </form>
      {slotsErr && (
        <div role="alert" data-testid="slots-error">
          <p style={{ color: "crimson" }}>{slotsErr.message}</p>
          {slotsErr.retryable && <button type="button" onClick={() => void sendLookup()} disabled={checking}>Retry availability</button>}
        </div>
      )}
      {checked && slots.length === 0 && <p>No open slots for that filter.</p>}
      {slots.length > 0 && (
        <fieldset>
          <legend>Open slots (fictional)</legend>
          {slots.map((s) => (
            <label key={s.slot_id} style={{ display: "block" }}>
              <input type="radio" name="slot" value={s.slot_id} checked={picked === s.slot_id} onChange={() => setPicked(s.slot_id)} />
              {" "}{s.date} {s.start} with {s.coach}
            </label>
          ))}
          <label style={{ display: "block", marginTop: 8 }}>
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            {" "}I confirm I want to request a hold on this slot (login required)
          </label>
          <button type="button" disabled={!picked || !confirmed || holding} onClick={() => void sendHold()}>
            {holding ? "Requesting..." : "Request hold"}
          </button>
        </fieldset>
      )}
      {holdMsg && (
        <div data-testid="hold-ok">
          <p>{holdMsg}</p>
          {activeHold && (
            <button type="button" onClick={() => void sendRelease()} disabled={releasing}>
              {releasing ? "Releasing hold..." : "Release hold"}
            </button>
          )}
        </div>
      )}
      {holdErr && (
        <div role="alert" data-testid="hold-error">
          <p style={{ color: "crimson" }}>{holdErr.message}</p>
          {holdErr.retryable && <button type="button" onClick={() => void sendHold()} disabled={holding}>Retry hold</button>}
        </div>
      )}
    </main>
  );
}
