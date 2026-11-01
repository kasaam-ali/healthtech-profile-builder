"use client";
import { FormEvent, useEffect, useState } from "react";
import { authed, tokenStore } from "../../lib/api";

type User = { id: number; email: string; full_name: string };
type Demographic = { date_of_birth: string | null; gender: string | null; city: string | null; country: string | null };
type Wellness = { activity_level: "low" | "moderate" | "high"; diet_notes: string | null; reminder_opt_in: boolean };
type Contact = { id: number; name: string; phone: string; relationship: string };

const emptyDemo: Demographic = { date_of_birth: null, gender: null, city: null, country: null };
const emptyWell: Wellness = { activity_level: "moderate", diet_notes: null, reminder_opt_in: false };
const emptyContact = { name: "", phone: "", relationship: "" };
const orNull = (v: string) => (v.trim() === "" ? null : v);

export default function Profile() {
  const [user, setUser] = useState<User | null>(null);
  const [demo, setDemo] = useState<Demographic>(emptyDemo);
  const [well, setWell] = useState<Wellness>(emptyWell);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [draft, setDraft] = useState(emptyContact);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const run = async (fn: () => Promise<void>, ok?: string) => {
    setError(""); setMsg("");
    try { await fn(); if (ok) setMsg(ok); } catch (e) { setError((e as Error).message); }
  };

  useEffect(() => {
    run(async () => {
      setUser(await authed<User>("/me"));
      setDemo((await authed<Demographic>("/me/demographic")) ?? emptyDemo);
      setWell((await authed<Wellness>("/me/wellness")) ?? emptyWell);
      setContacts((await authed<Contact[]>("/me/emergency-contacts")) ?? []);
    });
  }, []);

  const saveDemo = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const { date_of_birth, gender, city, country } = demo;
    setDemo((await authed<Demographic>("/me/demographic", "PUT", { date_of_birth, gender, city, country }))!);
  }, "Demographic saved."); };

  const saveWell = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const { activity_level, diet_notes, reminder_opt_in } = well;
    setWell((await authed<Wellness>("/me/wellness", "PUT", { activity_level, diet_notes, reminder_opt_in }))!);
  }, "Wellness saved."); };

  const addContact = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const c = (await authed<Contact>("/me/emergency-contacts", "POST", draft))!;
    setContacts([...contacts, c]); setDraft(emptyContact);
  }, "Contact added."); };

  const removeContact = (id: number) => run(async () => {
    await authed(`/me/emergency-contacts/${id}`, "DELETE");
    setContacts(contacts.filter((c) => c.id !== id));
  }, "Contact removed.");

  if (!user) return <main>{error ? <p style={{ color: "crimson" }}>{error}</p> : <p>Loading...</p>}</main>;
  return (
    <main>
      <h1>My profile</h1>
      <p><b>Name:</b> {user.full_name} <b>Email:</b> {user.email}</p>
      <p style={{ fontSize: 12 }}>Demo app: enter fictional data only.</p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {msg && <p style={{ color: "green" }}>{msg}</p>}

      <h2>Demographic</h2>
      <form onSubmit={saveDemo}>
        <label>Date of birth <input type="date" value={demo.date_of_birth ?? ""} onChange={(e) => setDemo({ ...demo, date_of_birth: orNull(e.target.value) })} /></label><br />
        <label>Gender <input value={demo.gender ?? ""} maxLength={40} onChange={(e) => setDemo({ ...demo, gender: orNull(e.target.value) })} /></label><br />
        <label>City <input value={demo.city ?? ""} maxLength={100} onChange={(e) => setDemo({ ...demo, city: orNull(e.target.value) })} /></label><br />
        <label>Country <input value={demo.country ?? ""} maxLength={100} onChange={(e) => setDemo({ ...demo, country: orNull(e.target.value) })} /></label><br />
        <button type="submit">Save demographic</button>
      </form>

      <h2>Wellness preferences</h2>
      <form onSubmit={saveWell}>
        <label>Activity level <select value={well.activity_level} onChange={(e) => setWell({ ...well, activity_level: e.target.value as Wellness["activity_level"] })}>
          <option value="low">low</option><option value="moderate">moderate</option><option value="high">high</option>
        </select></label><br />
        <label>Diet notes <input value={well.diet_notes ?? ""} maxLength={500} onChange={(e) => setWell({ ...well, diet_notes: orNull(e.target.value) })} /></label><br />
        <label><input type="checkbox" checked={well.reminder_opt_in} onChange={(e) => setWell({ ...well, reminder_opt_in: e.target.checked })} /> Send me reminders</label><br />
        <button type="submit">Save wellness</button>
      </form>

      <h2>Emergency contacts (max 5)</h2>
      <ul>
        {contacts.map((c) => (
          <li key={c.id}>{c.name} ({c.relationship}), {c.phone} <button onClick={() => removeContact(c.id)}>Remove</button></li>
        ))}
      </ul>
      <form onSubmit={addContact}>
        <input placeholder="Name" required maxLength={120} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <input placeholder="Phone, e.g. +92 300 0000000" required value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: e.target.value })} />
        <input placeholder="Relationship" required maxLength={40} value={draft.relationship} onChange={(e) => setDraft({ ...draft, relationship: e.target.value })} />
        <button type="submit">Add contact</button>
      </form>

      <p><button onClick={() => { tokenStore.clear(); location.href = "/login"; }}>Log out</button></p>
    </main>
  );
}
