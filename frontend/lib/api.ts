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
