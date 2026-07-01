"use client";

import { useEffect, useState } from "react";
import AuthGate from "../components/AuthGate";
import NavBar from "../components/NavBar";
import { api, Trade } from "@/lib/api";

function TradeRow({ trade }: { trade: Trade }) {
  const [open, setOpen] = useState(false);
  const pnlColor = (trade.pnl_usdt ?? 0) >= 0 ? "text-emerald-400" : "text-red-400";

  return (
    <div className="border-b border-zinc-800">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-zinc-900"
      >
        <div className="flex items-center gap-4">
          <span className="font-medium text-zinc-100">{trade.symbol}</span>
          <span className={`rounded px-2 py-0.5 text-xs ${trade.side === "long" ? "bg-emerald-900 text-emerald-300" : "bg-red-900 text-red-300"}`}>
            {trade.side.toUpperCase()}
          </span>
          <span className="text-xs text-zinc-500">{trade.strategy_name} / {trade.regime}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className={`text-sm font-medium ${pnlColor}`}>
            {trade.pnl_usdt != null ? `${trade.pnl_usdt.toFixed(2)} USDT` : "open"}
          </span>
          <span className="text-xs text-zinc-500">{new Date(trade.opened_at).toLocaleString()}</span>
        </div>
      </button>
      {open && (
        <div className="bg-zinc-900/50 px-4 py-4 text-sm">
          <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-4">
            <div><span className="text-zinc-500">Entry:</span> {trade.entry_price}</div>
            <div><span className="text-zinc-500">Exit:</span> {trade.exit_price ?? "—"}</div>
            <div><span className="text-zinc-500">SL:</span> {trade.stop_loss}</div>
            <div><span className="text-zinc-500">TP:</span> {trade.take_profit}</div>
          </div>
          <div className="mb-3">
            <div className="mb-1 font-medium text-zinc-300">Entry reasoning</div>
            <ul className="list-inside list-disc text-zinc-400">
              {trade.entry_reasoning.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </div>
          {trade.postmortem.length > 0 && (
            <div>
              <div className="mb-1 font-medium text-zinc-300">Post-mortem</div>
              <ul className="list-inside list-disc text-zinc-400">
                {trade.postmortem.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function JournalContent() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.trades().then(setTrades).catch(() => setError("Could not load trades"));
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <NavBar />
      <main className="mx-auto max-w-5xl px-6 py-8">
        <h1 className="mb-6 text-lg font-semibold">Trade Journal</h1>
        {error && <p className="text-sm text-red-400">{error}</p>}
        {!error && trades.length === 0 && <p className="text-sm text-zinc-500">No trades logged yet.</p>}
        <div className="rounded-lg border border-zinc-800">
          {trades.map((t) => <TradeRow key={t.id} trade={t} />)}
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <JournalContent />
    </AuthGate>
  );
}
