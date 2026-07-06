"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Button } from "../components/ui";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.login(password);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", minHeight: "100dvh", alignItems: "center", justifyContent: "center", background: "var(--bg)", padding: "0 16px" }}>
      <form onSubmit={handleSubmit} className="ui-card" style={{ width: "100%", maxWidth: 380, padding: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
          <span style={{ width: 30, height: 30, background: "var(--gradient-primary)", borderRadius: 8, display: "inline-block", flexShrink: 0, boxShadow: "0 4px 14px color-mix(in oklab, var(--accent) 45%, transparent)" }} />
          <h1 style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: "var(--text)", margin: 0 }}>Crypto Trading AI</h1>
        </div>
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          style={{
            width: "100%", marginBottom: 14, borderRadius: "var(--radius-sm)", border: "1px solid var(--border2)",
            background: "var(--surface2)", color: "var(--text)", padding: "12px 14px", fontSize: "var(--text-base)",
            outline: "none", transition: "border-color var(--dur-base) var(--ease-out-quart), box-shadow var(--dur-base) var(--ease-out-quart)",
          }}
          onFocus={e => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.boxShadow = "0 0 0 3px color-mix(in oklab, var(--accent) 25%, transparent)"; }}
          onBlur={e => { e.currentTarget.style.borderColor = "var(--border2)"; e.currentTarget.style.boxShadow = "none"; }}
        />
        {error && <p style={{ marginBottom: 14, fontSize: "var(--text-sm)", color: "var(--red)" }}>{error}</p>}
        <Button type="submit" variant="primary" disabled={loading} style={{ width: "100%", minHeight: 46 }}>
          {loading ? "Signing in..." : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
