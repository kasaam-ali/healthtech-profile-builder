"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { post, tokenStore } from "../../lib/api";

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      const t = await post<{ access_token: string }>("/auth/login", {
        email: f.get("email"), password: f.get("password"),
      });
      tokenStore.set(t.access_token);
      router.push("/profile");
    } catch (err) { setError((err as Error).message); }
  }

  return (
    <form onSubmit={onSubmit} style={{ display: "grid", gap: 8 }}>
      <h1>Log in</h1>
      <input name="email" type="email" placeholder="Email" required />
      <input name="password" type="password" placeholder="Password" required />
      <button type="submit">Log in</button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </form>
  );
}
