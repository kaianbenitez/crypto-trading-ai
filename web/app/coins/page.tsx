"use client";

import { useEffect, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import CoinDigestCard from "../components/CoinDigestCard";
import { api, CoinDigest } from "@/lib/api";

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
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Coin Watch</h1>
          <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>
            One plain-English read per coin, refreshed once a day (~9 PM PH): 24h price action, what the agent is watching for, and free news sentiment.
          </p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

        {loading ? (
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 32, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
            Loading…
          </div>
        ) : digests.length > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
            {digests.map(d => <CoinDigestCard key={d.symbol} digest={d} />)}
          </div>
        ) : (
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 32, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
            No digest yet — the agent builds one for every coin once a day, around 9 PM PH. Check back after the next run.
          </div>
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
