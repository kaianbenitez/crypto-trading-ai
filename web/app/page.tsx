"use client";

import { useEffect, useState } from "react";
import AuthGate from "./components/AuthGate";
import NavBar from "./components/NavBar";
import { api, Summary } from "@/lib/api";

function StatCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${accent || "text-zinc-100"}`}>{value}</div>
    </div>
  );
}

function DashboardContent() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const s = await api.summary();
      setSummary(s);
    } catch {
      setError("Could not load summary from backend");
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  async function toggleKillSwitch() {
    if (!summary) return;
    setToggling(true);
    try {
      await api.setKillSwitch(!summary.kill_switch_active, "manual toggle from dashboard");
      await load();
    } finally {
      setToggling(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <NavBar />
      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-lg font-semibold">Dashboard</h1>
          {summary && (
            <button
              onClick={toggleKillSwitch}
              disabled={toggling}
              className={`rounded px-4 py-2 text-sm font-medium ${
                summary.kill_switch_active
                  ? "bg-red-600 hover:bg-red-500"
                  : "bg-zinc-800 hover:bg-zinc-700 border border-zinc-700"
              }`}
            >
              {summary.kill_switch_active ? "Kill-switch ACTIVE — click to resume" : "Kill-switch off — click to halt"}
            </button>
          )}
        </div>

        {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

        {summary && (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Bankroll (USDT)" value={summary.bankroll_usdt.toFixed(2)} />
            <StatCard
              label="ROI"
              value={`${summary.roi_pct.toFixed(2)}%`}
              accent={summary.roi_pct >= 0 ? "text-emerald-400" : "text-red-400"}
            />
            <StatCard label="Win rate" value={`${summary.win_rate_pct.toFixed(1)}%`} />
            <StatCard label="Total trades" value={String(summary.total_trades)} />
            <StatCard label="Open positions" value={String(summary.open_positions)} />
            <StatCard
              label="Kill-switch"
              value={summary.kill_switch_active ? "ACTIVE" : "Off"}
              accent={summary.kill_switch_active ? "text-red-400" : "text-emerald-400"}
            />
          </div>
        )}
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <DashboardContent />
    </AuthGate>
  );
}
