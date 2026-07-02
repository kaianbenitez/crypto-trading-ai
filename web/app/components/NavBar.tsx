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
    <nav className="flex items-center justify-between border-b border-zinc-800 bg-[#171717] px-6 py-3">
      <div className="flex items-center gap-6">
        <span className="font-semibold text-zinc-100">Crypto Trading AI</span>
        <Link href="/" className="text-sm text-zinc-400 transition-colors hover:text-zinc-100">Dashboard</Link>
        <Link href="/journal" className="text-sm text-zinc-400 transition-colors hover:text-zinc-100">Journal</Link>
        <Link href="/signals" className="text-sm text-zinc-400 transition-colors hover:text-zinc-100">Signals</Link>
      </div>
      <button onClick={handleLogout} className="text-sm text-zinc-400 transition-colors hover:text-zinc-100">
        Logout
      </button>
    </nav>
  );
}
