export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Week 1 simplification: access token kept in sessionStorage (cleared when tab closes).
// See README "Limitations" for why httpOnly cookies are better in production.
export const tokenStore = {
  get: () => (typeof window === "undefined" ? null : sessionStorage.getItem("access_token")),
  set: (t: string) => sessionStorage.setItem("access_token", t),
  clear: () => sessionStorage.removeItem("access_token"),
};

export async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed");
  return data as T;
}

// Week 2: authenticated JSON request with the member Bearer token.
// The server derives ownership from the token; we never send user_id.
export async function authed<T>(path: string, method = "GET", body?: unknown): Promise<T | null> {
  const token = tokenStore.get();
  if (!token) throw new Error("Not logged in.");
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 404 && method === "GET") return null;
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { tokenStore.clear(); throw new Error("Session expired, please log in again."); }
  if (!res.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((e: { msg: string }) => e.msg).join("; ") : "Request failed");
  }
  return data as T;
}
