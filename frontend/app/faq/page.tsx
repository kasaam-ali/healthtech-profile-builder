"use client";
import { FormEvent, useState } from "react";
import { API } from "../../lib/api";
import { FaqAnswer, askFaq } from "../../lib/mlClient";

export default function FaqPage() {
  const [q, setQ] = useState("");
  const [a, setA] = useState<FaqAnswer | null>(null);
  const [error, setError] = useState("");
  const [retryable, setRetryable] = useState(false);
  const [pending, setPending] = useState(false);

  async function send(question: string) {
    if (pending) return;
    setError(""); setA(null); setRetryable(false); setPending(true);
    const r = await askFaq(API, question);
    setPending(false);
    if (r.ok) { setA(r.data); return; }
    setError(r.message);
    // A rejected question (422) needs editing, not a retry.
    setRetryable(r.kind !== "validation");
  }

  function ask(e: FormEvent) { e.preventDefault(); void send(q); }

  return (
    <main>
      <h1>Help FAQ</h1>
      <p>Answers come only from approved fictional policy text. Medical questions are not answered.</p>
      <form onSubmit={ask}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. How many emergency contacts can I add?" size={50} aria-label="Question" />
        <button type="submit" disabled={pending}>{pending ? "Asking..." : "Ask"}</button>
      </form>
      {error && (
        <div role="alert" data-testid="faq-error">
          <p style={{ color: "crimson" }}>{error}</p>
          {retryable && <button type="button" onClick={() => void send(q)} disabled={pending}>Retry</button>}
        </div>
      )}
      {a && (
        <div>
          <p>{a.abstained ? "Not answered: " : ""}{a.answer}</p>
          {a.sources.length > 0 && <p>Source: {a.sources.map((s) => s.title).join(", ")}</p>}
          <p><em>{a.disclaimer}</em></p>
        </div>
      )}
    </main>
  );
}
