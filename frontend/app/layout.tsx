import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = { title: "HealthTech Profile Builder" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", maxWidth: 480, margin: "40px auto", padding: 16 }}>
        <nav style={{ display: "flex", gap: 12, marginBottom: 24 }}>
          <Link href="/">Home</Link><Link href="/signup">Sign up</Link>
          <Link href="/login">Log in</Link><Link href="/profile">My profile</Link><Link href="/assistant">Assistant</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
