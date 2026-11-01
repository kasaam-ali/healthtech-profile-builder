"use client";
import { FormEvent, useState } from "react";
import { API } from "../../lib/api";

type Answer = { abstained: boolean; answer: string; sources: { id: string; title: string }[]; disclaimer: string };

export default function FaqPage() {
  const [q, setQ] = useState("");
  const [a, setA] = useState<Answer | null>(null);
  const [error, setError] = useState("");

  async function ask(e: FormEvent) {
    e.preventDefault(); setError(""); setA(null);
    const res = await fetch(`${API}/api/v1/faq`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
    const data = await res.json();
    if (!res.ok) { setError("Please enter a question between 3 and 500 characters."); return; }
    setA(data);
  }

  return (
    <main>
      <h1>Help FAQ</h1>
      <p>Answers come only from approved fictional policy text. Medical questions are not answered.</p>
      <form onSubmit={ask}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. How many emergency contacts can I add?" size={50} />
        <button type="submit">Ask</button>
      </form>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
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
