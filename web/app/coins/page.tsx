"use client";

import { useEffect, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import CoinDigestCard from "../components/CoinDigestCard";
import { api, CoinDigest } from "@/lib/api";
import { Card } from "../components/ui";

function CoinWatchContent() {
  const [digests, setDigests] = useState<CoinDigest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.coinDigests()
      .then(setDigests)
      .catch(() => setError("Could not load coin digests"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 1560, margin: "0 auto" }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0 }}>Coin Watch</h1>
          <p style={{ color: "var(--muted)", fontSize: "var(--text-xs)", margin: "4px 0 0" }}>
            One plain-English read per coin, refreshed once a day (~9 PM PH): 24h price action, what the agent is watching for, and free news sentiment.
          </p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: "var(--text-sm)", marginBottom: 12 }}>{error}</div>}

        {loading ? (
          <Card><div style={{ padding: 32, textAlign: "center", color: "var(--muted)", fontSize: "var(--text-sm)" }}>Loading…</div></Card>
        ) : digests.length > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
            {digests.map((d, i) => (
              <div key={d.symbol} className="rise-in" style={{ animationDelay: `${Math.min(i, 10) * 30}ms` }}>
                <CoinDigestCard digest={d} />
              </div>
            ))}
          </div>
        ) : (
          <Card><div style={{ padding: 32, textAlign: "center", color: "var(--muted)", fontSize: "var(--text-sm)" }}>
            No digest yet — the agent builds one for every coin once a day, around 9 PM PH. Check back after the next run.
          </div></Card>
        )}
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <CoinWatchContent />
    </AuthGate>
  );
}
