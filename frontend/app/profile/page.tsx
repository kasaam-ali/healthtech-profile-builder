"use client";
import { useEffect, useState } from "react";
import { API, tokenStore } from "../../lib/api";

type User = { id: number; email: string; full_name: string };

export default function Profile() {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) { setError("Not logged in."); return; }
    fetch(`${API}/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 401 ? "Session expired, please log in again." : "Error");
        setUser(await r.json());
      })
      .catch((e: Error) => { tokenStore.clear(); setError(e.message); });
  }, []);

  if (error) return <p style={{ color: "crimson" }}>{error}</p>;
  if (!user) return <p>Loading...</p>;
  return (
    <main>
      <h1>My profile</h1>
      <p><b>Name:</b> {user.full_name}</p>
      <p><b>Email:</b> {user.email}</p>
      <button onClick={() => { tokenStore.clear(); location.href = "/login"; }}>Log out</button>
    </main>
  );
}
