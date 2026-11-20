// Week 4: fetch helpers for the /assistant page (cited RAG FAQ and the two tools).
// Built on the Week 3 requestJson helper, so every call checks HTTP status, parses
// defensively, validates the response shape, and never throws.
import { Fail, Result, requestJson } from "./mlClient";

export type Citation = { doc_id: string; title: string; chunk_id: string; score: number };
export type RagAnswer = { abstained: boolean; reason: string | null; answer: string; citations: Citation[]; disclaimer: string };
export type Slot = { slot_id: string; date: string; start: string; coach: string };
export type Availability = { slots: Slot[]; disclaimer: string };
export type Hold = { hold_id: number; slot_id: string; status: string; note: string };

const isObj = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const isStr = (x: unknown): x is string => typeof x === "string";

export const isRagAnswer = (x: unknown): x is RagAnswer =>
  isObj(x) && typeof x.abstained === "boolean" && isStr(x.answer) && isStr(x.disclaimer) &&
  (x.reason === null || isStr(x.reason)) && Array.isArray(x.citations) &&
  x.citations.every((c) => isObj(c) && isStr(c.doc_id) && isStr(c.title) && isStr(c.chunk_id));

export const isAvailability = (x: unknown): x is Availability =>
  isObj(x) && isStr(x.disclaimer) && Array.isArray(x.slots) &&
  x.slots.every((s) => isObj(s) && isStr(s.slot_id) && isStr(s.date) && isStr(s.start) && isStr(s.coach));

export const isHold = (x: unknown): x is Hold =>
  isObj(x) && typeof x.hold_id === "number" && isStr(x.slot_id) && isStr(x.status) && isStr(x.note);

const json = (body: unknown, token?: string | null): RequestInit => {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return { method: "POST", headers, body: JSON.stringify(body) };
};

export const askRag = (api: string, question: string, token?: string | null, f: typeof fetch = fetch) =>
  requestJson(f, `${api}/api/v2/faq`, json({ question }, token), isRagAnswer, {
    unavailable: "Document retrieval is temporarily unavailable.",
    validation: "Please enter a question between 3 and 500 characters.",
  });

export const checkAvailability = (api: string, date: string, token?: string | null, f: typeof fetch = fetch) =>
  requestJson(f, `${api}/api/v2/tools/check_appointment_availability`, json(date ? { date } : {}, token), isAvailability, {
    unavailable: "Availability is temporarily unavailable.",
    validation: "Date must look like YYYY-MM-DD.",
  });

// The write tool: the server re-checks the JWT and human_confirmed; 400/401/409 carry a
// user-facing reason, 503 means the provider failed and nothing was written.
export async function requestHold(api: string, slotId: string, confirmed: boolean, token: string | null, f: typeof fetch = fetch): Promise<Result<Hold>> {
  if (!token) return { ok: false, kind: "validation", status: 401, message: "Please log in to request a hold." };
  const r = await requestJson(f, `${api}/api/v2/tools/request_appointment_hold`, json({ slot_id: slotId, human_confirmed: confirmed }, token), isHold, {
    unavailable: "Calendar provider unavailable. No hold was created.",
  });
  if (r.ok || r.kind !== "server") return r;
  const fail: Fail = r;
  if (fail.status === 401) return { ...fail, kind: "validation", message: "Your session expired. Please log in again." };
  if ((fail.status === 400 || fail.status === 409) && fail.detail) return { ...fail, kind: "validation", message: fail.detail };
  return fail;
}

export type ReleaseResult = { tool: string; hold_id: number; slot_id: string; status: string; note: string };
export const isReleaseResult = (x: unknown): x is ReleaseResult =>
  isObj(x) && typeof x.hold_id === "number" && isStr(x.slot_id) && isStr(x.status);

export async function releaseHold(api: string, holdId: number | string, token: string | null, f: typeof fetch = fetch): Promise<Result<ReleaseResult>> {
  if (!token) return { ok: false, kind: "validation", status: 401, message: "Please log in to release a hold." };
  const body = typeof holdId === "number" ? { hold_id: holdId } : { slot_id: holdId };
  const r = await requestJson(f, `${api}/api/v2/tools/release_appointment_hold`, json(body, token), isReleaseResult, {
    unavailable: "Calendar provider unavailable. Please try again.",
  });
  if (r.ok || r.kind !== "server") return r;
  const fail: Fail = r;
  if (fail.status === 401) return { ...fail, kind: "validation", message: "Your session expired. Please log in again." };
  if ((fail.status === 400 || fail.status === 404 || fail.status === 409) && fail.detail) return { ...fail, kind: "validation", message: fail.detail };
  return fail;
}

