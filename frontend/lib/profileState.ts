// Week 2: pure state helpers for the profile page, kept separate so they can be unit tested
// without a browser (see tests/profileState.test.js and `npm test`).

export type Contact = { id: number; name: string; phone: string; relationship: string };
export type FieldErrors = Record<string, string>;

// Every contact-list change is expressed as an updater over the latest state, so that two
// overlapping requests (e.g. add finishing while a remove finishes) never overwrite each other.
export const contactsAdd = (c: Contact) => (list: Contact[]): Contact[] =>
  list.some((x) => x.id === c.id) ? list : [...list, c];
export const contactsReplace = (c: Contact) => (list: Contact[]): Contact[] =>
  list.map((x) => (x.id === c.id ? c : x));
export const contactsRemove = (id: number) => (list: Contact[]): Contact[] =>
  list.filter((x) => x.id !== id);

// Pending keys ("add", "contact:3", "demo", "well") disable the matching controls while a
// request is in flight so the same action cannot be fired twice.
export const pendingAdd = (key: string) => (s: Set<string>): Set<string> => new Set(s).add(key);
export const pendingDone = (key: string) => (s: Set<string>): Set<string> => {
  const n = new Set(s); n.delete(key); return n;
};

// FastAPI 422 detail: [{loc: ["body", "phone"], msg: "Value error, ..."}] -> {phone: "..."}
export function fieldErrorsFrom(detail: unknown): FieldErrors {
  const out: FieldErrors = {};
  if (!Array.isArray(detail)) return out;
  for (const e of detail as { loc?: unknown[]; msg?: string }[]) {
    const loc = Array.isArray(e.loc) ? e.loc : [];
    const field = String(loc[loc.length - 1] ?? "form");
    out[field] = String(e.msg ?? "Invalid value").replace(/^Value error, /, "");
  }
  return out;
}
