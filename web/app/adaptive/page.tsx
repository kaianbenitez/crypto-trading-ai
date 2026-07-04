"use client";

import { useEffect, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import CoinLogo from "../components/CoinLogo";
import { api, CoinBrain, AdaptiveActivityEntry } from "@/lib/api";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontWeight: 600, fontSize: 12, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)" }}>{title}</div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  );
}

function BrainCard({ brain }: { brain: CoinBrain }) {
  return (
    <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <CoinLogo symbol={brain.symbol} size={18} />
        <span style={{ fontWeight: 700, fontSize: 12 }}>{brain.symbol.replace("/USDT", "")}</span>
        <span style={{ color: "var(--muted)", fontSize: 10, marginLeft: "auto" }}>v{brain.version}</span>
      </div>
      <div style={{ color: "var(--muted)", fontSize: 11 }}>
        {brain.disabled_legs.length > 0 ? (
          <>Paused: {brain.disabled_legs.join(", ")}</>
        ) : (
          "All strategy styles active for this coin"
        )}
      </div>
      <div style={{ color: "var(--muted)", fontSize: 10, marginTop: 4 }}>
        Updated {new Date(brain.updated_at).toLocaleDateString([], { month: "short", day: "numeric" })}
      </div>
    </div>
  );
}

function ActivityRow({ entry }: { entry: AdaptiveActivityEntry }) {
  const icon = entry.type === "trail_move" ? "🛡" : "🧠";
  return (
    <div style={{ display: "flex", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ fontSize: 14 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12 }}>
          <b>{entry.symbol}</b> — {entry.message}
        </div>
        <div style={{ color: "var(--muted)", fontSize: 10, marginTop: 2 }}>
          {new Date(entry.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>
    </div>
  );
}

function AdaptiveContent() {
  const [brains, setBrains] = useState<CoinBrain[]>([]);
  const [activity, setActivity] = useState<AdaptiveActivityEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.coinBrains(), api.adaptiveActivity(50)])
      .then(([b, a]) => { setBrains(b); setActivity(a); })
      .catch(() => setError("Could not load adaptive data"));
  }, []);

  return (
    <div style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main style={{ flex: 1, minWidth: 0, maxWidth: 1200, margin: "0 auto", padding: "28px 28px 60px" }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Adaptive</h1>
          <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>
            What the agent has quietly learned per coin — which strategy styles it's paused, and a log of every parameter/trailing-stop change it made on its own.
          </p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Per-coin brain state">
            {brains.length > 0 ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
                {brains.map(b => <BrainCard key={b.symbol} brain={b} />)}
              </div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 13 }}>No per-coin adjustments yet.</div>
            )}
          </Card>

          <Card title="Recent activity">
            {activity.length > 0 ? (
              <div>{activity.map((entry, i) => <ActivityRow key={i} entry={entry} />)}</div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 13 }}>No adaptive activity logged yet.</div>
            )}
          </Card>
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <AdaptiveContent />
    </AuthGate>
  );
}
