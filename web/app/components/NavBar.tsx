"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NavBar() {
  const router = useRouter();

  async function handleLogout() {
    await api.logout().catch(() => {});
    router.push("/login");
  }

  return (
    <nav style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)", padding: "0 24px", height: 52, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text)", textDecoration: "none" }}>
          <span style={{ width: 20, height: 20, background: "var(--accent)", borderRadius: 5, display: "inline-block" }} />
          <span style={{ fontWeight: 700, fontSize: 14 }}>TradingAI</span>
        </Link>
        <Link href="/" style={{ color: "var(--muted)", fontSize: 13, textDecoration: "none" }}>Dashboard</Link>
        <Link href="/journal" style={{ color: "var(--muted)", fontSize: 13, textDecoration: "none" }}>Journal</Link>
      </div>
      <button onClick={handleLogout} style={{ background: "transparent", border: 0, color: "var(--muted)", cursor: "pointer", fontSize: 13 }}>
        Logout
      </button>
    </nav>
  );
}
