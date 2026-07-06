"use client";

import { useEffect, useState } from "react";
import { Brain, ShieldCheck } from "@phosphor-icons/react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import CoinLogo from "../components/CoinLogo";
import { api, CoinBrain, AdaptiveActivityEntry } from "@/lib/api";
import { Card } from "../components/ui";

function BrainCard({ brain }: { brain: CoinBrain }) {
  return (
    <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <CoinLogo symbol={brain.symbol} size={18} />
        <span style={{ fontWeight: 700, fontSize: "var(--text-xs)" }}>{brain.symbol.replace("/USDT", "")}</span>
        <span style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginLeft: "auto" }}>v{brain.version}</span>
      </div>
      <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>
        {brain.disabled_legs.length > 0 ? (
          <>Paused: {brain.disabled_legs.join(", ")}</>
        ) : (
          "All strategy styles active for this coin"
        )}
      </div>
      <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 4 }}>
        Updated {new Date(brain.updated_at).toLocaleDateString([], { month: "short", day: "numeric" })}
      </div>
    </div>
  );
}

function ActivityRow({ entry }: { entry: AdaptiveActivityEntry }) {
  const Icon = entry.type === "trail_move" ? ShieldCheck : Brain;
  return (
    <div style={{ display: "flex", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
      <Icon size={15} style={{ flexShrink: 0, marginTop: 1, color: "var(--accent)" }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-xs)" }}>
          <b>{entry.symbol}</b> — {entry.message}
        </div>
        <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 2 }}>
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
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 1200, margin: "0 auto" }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0 }}>Adaptive</h1>
          <p style={{ color: "var(--muted)", fontSize: "var(--text-xs)", margin: "4px 0 0" }}>
            What the agent has quietly learned per coin — which strategy styles it&apos;s paused, and a log of every parameter/trailing-stop change it made on its own.
          </p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: "var(--text-sm)", marginBottom: 12 }}>{error}</div>}

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Per-coin brain state">
            {brains.length > 0 ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
                {brains.map(b => <BrainCard key={b.symbol} brain={b} />)}
              </div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>No per-coin adjustments yet.</div>
            )}
          </Card>

          <Card title="Recent activity">
            {activity.length > 0 ? (
              <div>{activity.map((entry, i) => <ActivityRow key={i} entry={entry} />)}</div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>No adaptive activity logged yet.</div>
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
