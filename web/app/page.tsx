"use client";

import { useEffect, useMemo, useState } from "react";
import AuthGate from "./components/AuthGate";
import NavBar from "./components/NavBar";
import { AgentStatus, api, Summary, Trade } from "@/lib/api";

const money = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function serviceText(value?: string) {
  if (!value) return "unknown";
  return value === "active" ? "online" : value;
}

function serviceClass(value?: string) {
  if (value === "active") return "text-emerald-300";
  if (value === "inactive" || value === "failed") return "text-red-300";
  return "text-zinc-400";
}

function pnlClass(value: number) {
  if (value > 0) return "text-emerald-300";
  if (value < 0) return "text-red-300";
  return "text-zinc-100";
}

function Cell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="min-w-0 border-r border-zinc-800/80 px-4 py-3 last:border-r-0">
      <div className="text-[13px] text-zinc-500">{label}</div>
      <div className={`mt-1 truncate text-[15px] font-medium ${tone || "text-zinc-100"}`}>{value}</div>
    </div>
  );
}

function ServiceRow({ name, state }: { name: string; state?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-zinc-800/70 py-2 last:border-b-0">
      <span className="text-sm text-zinc-300">{name}</span>
      <span className={`text-sm font-medium ${serviceClass(state)}`}>{serviceText(state)}</span>
    </div>
  );
}

function RecentTrade({ trade }: { trade: Trade }) {
  const pnl = trade.pnl_usdt ?? 0;
  const status = trade.closed_at ? trade.outcome || "closed" : "open";

  return (
    <div className="grid grid-cols-[1fr_auto] gap-4 border-b border-zinc-800/70 py-3 last:border-b-0">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium text-zinc-100">{trade.symbol}</span>
          <span className={trade.side === "long" ? "text-emerald-300" : "text-red-300"}>
            {trade.side}
          </span>
          <span className="text-zinc-500">{trade.strategy_name}</span>
        </div>
        <div className="mt-1 truncate text-sm text-zinc-500">
          {trade.entry_reasoning[0] || "No entry reason recorded"}
        </div>
      </div>
      <div className="text-right">
        <div className={`text-sm font-medium ${trade.closed_at ? pnlClass(pnl) : "text-amber-300"}`}>
          {trade.closed_at ? `${pnl >= 0 ? "+" : ""}${money.format(pnl)} USDT` : "open"}
        </div>
        <div className="mt-1 text-sm text-zinc-500">{status}</div>
      </div>
    </div>
  );
}

function OpenPosition({ trade }: { trade: Trade }) {
  const reason = trade.entry_reasoning[0] || "No entry reason recorded";

  return (
    <div className="border-b border-zinc-800/70 py-3 last:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium text-zinc-100">{trade.symbol}</span>
          <span className={trade.side === "long" ? "text-emerald-300" : "text-red-300"}>
            {trade.side}
          </span>
          <span className="text-zinc-500">{trade.strategy_name}</span>
        </div>
        <span className="text-sm text-amber-300">open</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2 text-sm md:grid-cols-4">
        <div>
          <span className="text-zinc-500">Entry </span>
          <span className="text-zinc-200">{trade.entry_price}</span>
        </div>
        <div>
          <span className="text-zinc-500">SL </span>
          <span className="text-zinc-200">{trade.stop_loss}</span>
        </div>
        <div>
          <span className="text-zinc-500">TP </span>
          <span className="text-zinc-200">{trade.take_profit}</span>
        </div>
        <div>
          <span className="text-zinc-500">Lev </span>
          <span className="text-zinc-200">{trade.leverage}x</span>
        </div>
      </div>
      <div className="mt-2 truncate text-sm text-zinc-500">{reason}</div>
    </div>
  );
}

function DashboardContent() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [summaryResult, statusResult, tradesResult] = await Promise.all([
        api.summary(),
        api.agentStatus(),
        api.trades(5),
      ]);
      setSummary(summaryResult);
      setStatus(statusResult);
      setTrades(tradesResult);
      setError(null);
    } catch {
      setError("Could not load dashboard data");
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

  const lastChecked = useMemo(() => {
    if (!status?.checked_at) return "not checked";
    return new Date(status.checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }, [status?.checked_at]);

  const openTrades = trades.filter((trade) => !trade.closed_at);
  const closedTrades = trades.filter((trade) => trade.closed_at);

  return (
    <div className="min-h-screen bg-[#0f0f0f] text-zinc-100">
      <NavBar />
      <main className="mx-auto max-w-6xl px-6 py-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-semibold text-zinc-50">Dashboard</h1>
            <p className="mt-1 text-sm text-zinc-500">
              Binance Futures testnet, ETH/XRP only. Last check {lastChecked}.
            </p>
          </div>
          {summary && (
            <button
              onClick={toggleKillSwitch}
              disabled={toggling}
              className={`rounded-md border px-4 py-2 text-sm font-medium transition-colors ${
                summary.kill_switch_active
                  ? "border-red-500/50 bg-red-500/15 text-red-200 hover:bg-red-500/20"
                  : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
              }`}
            >
              {summary.kill_switch_active ? "Resume trading" : "Halt new entries"}
            </button>
          )}
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-red-900/70 bg-red-950/30 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        )}

        <section className="mb-5 overflow-hidden rounded-lg border border-zinc-800 bg-[#171717]">
          <div className="grid grid-cols-2 md:grid-cols-6">
            <Cell label="Agent" value={serviceText(status?.trading_agent)} tone={serviceClass(status?.trading_agent)} />
            <Cell label="Mode" value={status?.testnet ? "testnet" : "live"} tone={status?.testnet ? "text-amber-300" : "text-red-300"} />
            <Cell label="Bankroll" value={`${money.format(summary?.bankroll_usdt ?? status?.bankroll_usdt ?? 0)} USDT`} />
            <Cell label="ROI" value={`${(summary?.roi_pct ?? 0).toFixed(2)}%`} tone={pnlClass(summary?.roi_pct ?? 0)} />
            <Cell label="Win rate" value={`${(summary?.win_rate_pct ?? 0).toFixed(1)}%`} />
            <Cell label="Open positions" value={String(summary?.open_positions ?? 0)} tone={(summary?.open_positions ?? 0) > 0 ? "text-amber-300" : "text-zinc-100"} />
          </div>
        </section>

        <div className="grid gap-5 lg:grid-cols-[1.35fr_0.65fr]">
          <section className="rounded-lg border border-zinc-800 bg-[#171717]">
            <div className="border-b border-zinc-800 px-4 py-3">
              <div className="font-medium text-zinc-100">Trading state</div>
            </div>
            <div className="grid gap-0 md:grid-cols-2">
              <div className="border-b border-zinc-800 p-4 md:border-b-0 md:border-r">
                <div className="grid grid-cols-2 gap-x-5 gap-y-4">
                  <div>
                    <div className="text-sm text-zinc-500">Exchange</div>
                    <div className="mt-1 text-sm font-medium text-zinc-100">{status?.exchange || "binance"}</div>
                  </div>
                  <div>
                    <div className="text-sm text-zinc-500">Kill switch</div>
                    <div className={`mt-1 text-sm font-medium ${summary?.kill_switch_active ? "text-red-300" : "text-emerald-300"}`}>
                      {summary?.kill_switch_active ? "on" : "off"}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-zinc-500">Symbols</div>
                    <div className="mt-1 text-sm font-medium text-zinc-100">
                      {(status?.symbols || ["ETH/USDT", "XRP/USDT"]).join(", ")}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-zinc-500">Closed trades</div>
                    <div className="mt-1 text-sm font-medium text-zinc-100">{summary?.total_trades ?? 0}</div>
                  </div>
                </div>
              </div>
              <div className="p-4">
                <ServiceRow name="Trading agent" state={status?.trading_agent} />
                <ServiceRow name="Backend" state={status?.webapi} />
                <ServiceRow name="Dashboard" state={status?.dashboard} />
                <ServiceRow name="Nginx" state={status?.nginx} />
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-zinc-800 bg-[#171717]">
            <div className="border-b border-zinc-800 px-4 py-3">
              <div className="font-medium text-zinc-100">Risk</div>
            </div>
            <div className="space-y-3 p-4 text-sm">
              <div className="flex justify-between gap-4">
                <span className="text-zinc-500">Risk per trade</span>
                <span className="font-medium text-zinc-100">1.5%</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-zinc-500">Max daily drawdown</span>
                <span className="font-medium text-zinc-100">5%</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-zinc-500">Default leverage</span>
                <span className="font-medium text-zinc-100">3x</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-zinc-500">Max positions</span>
                <span className="font-medium text-zinc-100">1</span>
              </div>
            </div>
          </section>
        </div>

        <section className="mt-5 rounded-lg border border-zinc-800 bg-[#171717]">
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div className="font-medium text-zinc-100">Open positions</div>
            <span className="text-sm text-zinc-500">{openTrades.length}</span>
          </div>
          <div className="px-4">
            {openTrades.length > 0 ? (
              openTrades.map((trade) => <OpenPosition key={trade.id} trade={trade} />)
            ) : (
              <div className="py-5 text-sm text-zinc-500">No active positions.</div>
            )}
          </div>
        </section>

        <section className="mt-5 rounded-lg border border-zinc-800 bg-[#171717]">
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div className="font-medium text-zinc-100">Recent closed trades</div>
            <a href="/journal" className="text-sm text-zinc-400 hover:text-zinc-100">
              Open journal
            </a>
          </div>
          <div className="px-4">
            {closedTrades.length > 0 ? (
              closedTrades.map((trade) => <RecentTrade key={trade.id} trade={trade} />)
            ) : (
              <div className="py-5 text-sm text-zinc-500">No closed trades yet.</div>
            )}
          </div>
        </section>
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
