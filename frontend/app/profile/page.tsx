"use client";
import { FormEvent, useEffect, useState } from "react";
import { ApiError, authed, tokenStore } from "../../lib/api";
import {
  Contact, FieldErrors, contactsAdd, contactsRemove, contactsReplace, fieldErrorsFrom,
  pendingAdd, pendingDone,
} from "../../lib/profileState";

type User = { id: number; email: string; full_name: string };
type Demographic = { date_of_birth: string | null; gender: string | null; city: string | null; country: string | null };
type Wellness = { activity_level: "low" | "moderate" | "high"; diet_notes: string | null; reminder_opt_in: boolean };
type Draft = { name: string; phone: string; relationship: string };

const emptyDemo: Demographic = { date_of_birth: null, gender: null, city: null, country: null };
const emptyWell: Wellness = { activity_level: "moderate", diet_notes: null, reminder_opt_in: false };
const emptyContact: Draft = { name: "", phone: "", relationship: "" };
const orNull = (v: string) => (v.trim() === "" ? null : v);
const errStyle = { color: "crimson", fontSize: 12, margin: 0 };

function FieldError({ id, msg }: { id: string; msg?: string }) {
  return msg ? <p id={id} role="alert" style={errStyle}>{msg}</p> : null;
}

// Labeled contact inputs used for both "add" and "edit" (labels, not placeholders alone).
function ContactFields({ prefix, value, onChange, errors, disabled }: {
  prefix: string; value: Draft; onChange: (d: Draft) => void; errors: FieldErrors; disabled: boolean;
}) {
  const field = (key: keyof Draft, label: string, extra: object) => (
    <div>
      <label htmlFor={`${prefix}-${key}`}>{label}</label>{" "}
      <input id={`${prefix}-${key}`} required disabled={disabled} value={value[key]}
        aria-invalid={!!errors[key]} aria-describedby={errors[key] ? `${prefix}-${key}-err` : undefined}
        onChange={(e) => onChange({ ...value, [key]: e.target.value })} {...extra} />
      <FieldError id={`${prefix}-${key}-err`} msg={errors[key]} />
    </div>
  );
  return (
    <>
      {field("name", "Name", { maxLength: 120 })}
      {field("phone", "Phone", { inputMode: "tel", maxLength: 30, placeholder: "+92 300 0000000" })}
      {field("relationship", "Relationship", { maxLength: 40 })}
    </>
  );
}

export default function Profile() {
  const [user, setUser] = useState<User | null>(null);
  const [demo, setDemo] = useState<Demographic>(emptyDemo);
  const [well, setWell] = useState<Wellness>(emptyWell);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyContact);
  const [editing, setEditing] = useState<{ id: number; draft: Draft } | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [fieldErrors, setFieldErrors] = useState<Record<string, FieldErrors>>({});
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  // Runs one request under a pending key; 422s become field errors for that form.
  const run = async (key: string, fn: () => Promise<void>, ok?: string) => {
    setError(""); setMsg("");
    setPending(pendingAdd(key));
    setFieldErrors((f) => ({ ...f, [key]: {} }));
    try { await fn(); if (ok) setMsg(ok); }
    catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        setFieldErrors((f) => ({ ...f, [key]: fieldErrorsFrom(e.detail) }));
        setError("Please fix the highlighted fields.");
      } else setError((e as Error).message);
    } finally { setPending(pendingDone(key)); }
  };
  const busy = (key: string) => pending.has(key);
  const errs = (key: string) => fieldErrors[key] ?? {};

  useEffect(() => {
    run("load", async () => {
      setUser(await authed<User>("/me"));
      setDemo((await authed<Demographic>("/me/demographic")) ?? emptyDemo);
      setWell((await authed<Wellness>("/me/wellness")) ?? emptyWell);
      setContacts((await authed<Contact[]>("/me/emergency-contacts")) ?? []);
    });
  }, []);

  const saveDemo = (e: FormEvent) => { e.preventDefault(); run("demo", async () => {
    const { date_of_birth, gender, city, country } = demo;
    setDemo((await authed<Demographic>("/me/demographic", "PUT", { date_of_birth, gender, city, country }))!);
  }, "Demographic saved."); };

  const deleteDemo = () => {
    if (!window.confirm("Delete your demographic section? This cannot be undone.")) return;
    run("demo", async () => { await authed("/me/demographic", "DELETE"); setDemo(emptyDemo); }, "Demographic deleted.");
  };

  const saveWell = (e: FormEvent) => { e.preventDefault(); run("well", async () => {
    const { activity_level, diet_notes, reminder_opt_in } = well;
    setWell((await authed<Wellness>("/me/wellness", "PUT", { activity_level, diet_notes, reminder_opt_in }))!);
  }, "Wellness saved."); };

  const deleteWell = () => {
    if (!window.confirm("Delete your wellness preferences? This cannot be undone.")) return;
    run("well", async () => { await authed("/me/wellness", "DELETE"); setWell(emptyWell); }, "Wellness deleted.");
  };

  const addContact = (e: FormEvent) => { e.preventDefault(); run("add", async () => {
    const c = (await authed<Contact>("/me/emergency-contacts", "POST", draft))!;
    setContacts(contactsAdd(c)); setDraft(emptyContact);
  }, "Contact added."); };

  const saveEdit = (e: FormEvent) => { e.preventDefault(); if (!editing) return;
    const { id, draft: d } = editing;
    run(`contact:${id}`, async () => {
      const c = (await authed<Contact>(`/me/emergency-contacts/${id}`, "PUT", d))!;
      setContacts(contactsReplace(c)); setEditing(null);
    }, "Contact updated.");
  };

  const removeContact = (c: Contact) => {
    if (!window.confirm(`Remove emergency contact ${c.name}?`)) return;
    run(`contact:${c.id}`, async () => {
      await authed(`/me/emergency-contacts/${c.id}`, "DELETE");
      setContacts(contactsRemove(c.id));
      setEditing((ed) => (ed?.id === c.id ? null : ed));
    }, "Contact removed.");
  };

  if (!user) return <main>{error ? <p style={{ color: "crimson" }}>{error}</p> : <p>Loading...</p>}</main>;
  return (
    <main>
      <h1>My profile</h1>
      <p><b>Name:</b> {user.full_name} <b>Email:</b> {user.email}</p>
      <p style={{ fontSize: 12 }}>Demo app: enter fictional data only.</p>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      {msg && <p role="status" style={{ color: "green" }}>{msg}</p>}

      <h2>Demographic</h2>
      <form onSubmit={saveDemo} aria-busy={busy("demo")}>
        <label>Date of birth <input type="date" value={demo.date_of_birth ?? ""} onChange={(e) => setDemo({ ...demo, date_of_birth: orNull(e.target.value) })} /></label>
        <FieldError id="demo-dob-err" msg={errs("demo").date_of_birth} /><br />
        <label>Gender <input value={demo.gender ?? ""} maxLength={40} onChange={(e) => setDemo({ ...demo, gender: orNull(e.target.value) })} /></label>
        <FieldError id="demo-gender-err" msg={errs("demo").gender} /><br />
        <label>City <input value={demo.city ?? ""} maxLength={100} onChange={(e) => setDemo({ ...demo, city: orNull(e.target.value) })} /></label>
        <FieldError id="demo-city-err" msg={errs("demo").city} /><br />
        <label>Country <input value={demo.country ?? ""} maxLength={100} onChange={(e) => setDemo({ ...demo, country: orNull(e.target.value) })} /></label>
        <FieldError id="demo-country-err" msg={errs("demo").country} /><br />
        <button type="submit" disabled={busy("demo")}>Save demographic</button>{" "}
        <button type="button" disabled={busy("demo")} onClick={deleteDemo}>Delete demographic</button>
      </form>

      <h2>Wellness preferences</h2>
      <form onSubmit={saveWell} aria-busy={busy("well")}>
        <label>Activity level <select value={well.activity_level} onChange={(e) => setWell({ ...well, activity_level: e.target.value as Wellness["activity_level"] })}>
          <option value="low">low</option><option value="moderate">moderate</option><option value="high">high</option>
        </select></label>
        <FieldError id="well-activity-err" msg={errs("well").activity_level} /><br />
        <label>Diet notes <input value={well.diet_notes ?? ""} maxLength={500} onChange={(e) => setWell({ ...well, diet_notes: orNull(e.target.value) })} /></label>
        <FieldError id="well-diet-err" msg={errs("well").diet_notes} /><br />
        <label><input type="checkbox" checked={well.reminder_opt_in} onChange={(e) => setWell({ ...well, reminder_opt_in: e.target.checked })} /> Send me reminders</label><br />
        <button type="submit" disabled={busy("well")}>Save wellness</button>{" "}
        <button type="button" disabled={busy("well")} onClick={deleteWell}>Delete wellness</button>
      </form>

      <h2>Emergency contacts (max 5)</h2>
      <ul>
        {contacts.map((c) => {
          const key = `contact:${c.id}`;
          return (
            <li key={c.id}>
              {editing?.id === c.id ? (
                <form onSubmit={saveEdit} aria-label={`Edit contact ${c.name}`}>
                  <ContactFields prefix={`edit-${c.id}`} value={editing.draft} errors={errs(key)} disabled={busy(key)}
                    onChange={(d) => setEditing({ id: c.id, draft: d })} />
                  <button type="submit" disabled={busy(key)}>Save contact</button>{" "}
                  <button type="button" disabled={busy(key)} onClick={() => setEditing(null)}>Cancel</button>
                </form>
              ) : (
                <>
                  {c.name} ({c.relationship}), {c.phone}{" "}
                  <button disabled={busy(key)} aria-label={`Edit ${c.name}`}
                    onClick={() => setEditing({ id: c.id, draft: { name: c.name, phone: c.phone, relationship: c.relationship } })}>Edit</button>{" "}
                  <button disabled={busy(key)} aria-label={`Remove ${c.name}`} onClick={() => removeContact(c)}>Remove</button>
                </>
              )}
            </li>
          );
        })}
      </ul>
      <h3>Add contact</h3>
      <form onSubmit={addContact} aria-busy={busy("add")}>
        <ContactFields prefix="new" value={draft} onChange={setDraft} errors={errs("add")} disabled={busy("add")} />
        <button type="submit" disabled={busy("add") || contacts.length >= 5}>Add contact</button>
      </form>

      <p><button onClick={() => { tokenStore.clear(); location.href = "/login"; }}>Log out</button></p>
    </main>
  );
}
