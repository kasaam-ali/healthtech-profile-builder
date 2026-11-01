"use client";
import { FormEvent, useState } from "react";
import { API, authed, tokenStore } from "../../lib/api";

type Citation = { doc_id: string; title: string; chunk_id: string; score: number };
type Answer = { abstained: boolean; reason: string | null; answer: string; citations: Citation[]; disclaimer: string };
type Slot = { slot_id: string; date: string; start: string; coach: string };

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed");
  return data as T;
}

export default function AssistantPage() {
  const [q, setQ] = useState("");
  const [a, setA] = useState<Answer | null>(null);
  const [date, setDate] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [picked, setPicked] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function ask(e: FormEvent) {
    e.preventDefault(); setError(""); setA(null);
    try { setA(await postJson<Answer>("/api/v2/faq", { question: q })); }
    catch (err) { setError((err as Error).message); }
  }

  async function lookup(e: FormEvent) {
    e.preventDefault(); setError(""); setMsg(""); setPicked(""); setConfirmed(false);
    try {
      const d = await postJson<{ slots: Slot[] }>("/api/v2/tools/check_appointment_availability", date ? { date } : {});
      setSlots(d.slots);
      if (d.slots.length === 0) setMsg("No open slots for that filter.");
    } catch (err) { setError((err as Error).message); }
  }

  async function hold() {
    setError(""); setMsg("");
    try {
      const d = await authed<{ slot_id: string; note: string }>("/api/v2/tools/request_appointment_hold", "POST",
        { slot_id: picked, human_confirmed: confirmed });
      setMsg(`Hold requested for ${d?.slot_id}. ${d?.note}`);
      setSlots(slots.filter((s) => s.slot_id !== picked)); setPicked(""); setConfirmed(false);
    } catch (err) { setError((err as Error).message); }
  }

  return (
    <main>
      <h1>Clinic assistant</h1>
      <p>Answers cite approved fictional clinic documents. Medical questions are not answered.</p>
      <form onSubmit={ask}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. How long does a hold last?" size={40} />
        <button type="submit">Ask</button>
      </form>
      {a && (
        <section>
          <p>{a.abstained ? "Not answered: " : ""}{a.answer}</p>
          {a.citations.length > 0 && (
            <ul>{a.citations.map((c) => <li key={c.chunk_id}>{c.doc_id}: {c.title} ({c.chunk_id})</li>)}</ul>
          )}
          <p><em>{a.disclaimer}</em></p>
        </section>
      )}

      <h2>Appointment availability</h2>
      <form onSubmit={lookup}>
        <input value={date} onChange={(e) => setDate(e.target.value)} placeholder="YYYY-MM-DD (optional)" />
        <button type="submit">Check</button>
      </form>
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
          <button type="button" disabled={!picked || !confirmed} onClick={hold}>Request hold</button>
        </fieldset>
      )}
      {msg && <p>{msg}</p>}
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
    </main>
  );
}
