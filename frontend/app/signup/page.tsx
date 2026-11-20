"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { post } from "../../lib/api";

export default function Signup() {
  const router = useRouter();
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await post("/auth/signup", {
        full_name: f.get("full_name"), email: f.get("email"), password: f.get("password"),
      });
      router.push("/login");
    } catch (err) { setError((err as Error).message); }
  }

  return (
    <form onSubmit={onSubmit} style={{ display: "grid", gap: 8 }}>
      <h1>Sign up</h1>
      <input name="full_name" placeholder="Full name" required />
      <input name="email" type="email" placeholder="Email" required />
      <input name="password" type="password" placeholder="Password (min 8)" minLength={8} required />
      <button type="submit">Create account</button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </form>
  );
}
