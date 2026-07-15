"use client";

import { useEffect, useMemo, useState } from "react";
import { DownloadSimple, GearSix } from "@phosphor-icons/react";
import AuthGate from "../components/AuthGate";
import { api, Trade as ApiTrade, TradeNarrative } from "@/lib/api";

function money(value: number | null | undefined) { return value == null ? "—" : `${value >= 0 ? "+" : "-"}$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
function shortSymbol(value: string) { return value.replace("/USDT:USDT", "").replace("/USDT", "").replace("USDT", ""); }

function JournalContent() {
  const [trades, setTrades] = useState<ApiTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [narrative, setNarrative] = useState<TradeNarrative | null>(null);
  const [coin, setCoin] = useState("All Coins");
  const [strategy, setStrategy] = useState("All Strategies");
  const [exitReason, setExitReason] = useState("All Exit Reasons");

  useEffect(() => {
    api.trades(500).then((items) => {
      const closed = items.filter((item) => item.closed_at);
      setTrades(closed);
      setSelectedId((current) => current ?? closed[0]?.id ?? null);
      setLoadError(null);
    }).catch(() => setLoadError("Could not load trades from the backend.")).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedId == null) { setNarrative(null); return; }
    let active = true;
    api.tradeNarrative(selectedId).then((n) => active && setNarrative(n)).catch(() => active && setNarrative(null));
    return () => { active = false; };
  }, [selectedId]);

  const coins = useMemo(() => Array.from(new Set(trades.map((t) => shortSymbol(t.symbol)))).sort(), [trades]);
  const strategies = useMemo(() => Array.from(new Set(trades.map((t) => t.strategy_name))).sort(), [trades]);
  const exitReasons = useMemo(() => Array.from(new Set(trades.map((t) => t.exit_reason).filter(Boolean))) as string[], [trades]);

  const visible = useMemo(() => trades.filter((t) =>
    (coin === "All Coins" || shortSymbol(t.symbol) === coin) &&
    (strategy === "All Strategies" || t.strategy_name === strategy) &&
    (exitReason === "All Exit Reasons" || t.exit_reason === exitReason)
  ), [trades, coin, strategy, exitReason]);

  const selected = trades.find((t) => t.id === selectedId) ?? trades[0];

  const stats = useMemo(() => {
    if (!visible.length) return null;
    const netPnl = visible.reduce((sum, t) => sum + (t.pnl_usdt ?? 0), 0);
    const wins = visible.filter((t) => (t.pnl_usdt ?? 0) > 0).length;
    return { netPnl, winRatePct: (wins / visible.length) * 100, wins, sampleSize: visible.length };
  }, [visible]);

  const byStrategy = useMemo(() => {
    const map = new Map<string, { n: number; wins: number; pnl: number }>();
    for (const t of visible) {
      const s = map.get(t.strategy_name) ?? { n: 0, wins: 0, pnl: 0 };
      s.n += 1;
      s.pnl += t.pnl_usdt ?? 0;
      if ((t.pnl_usdt ?? 0) > 0) s.wins += 1;
      map.set(t.strategy_name, s);
    }
    return Array.from(map.entries()).map(([name, s]) => ({ name, ...s, winRatePct: (s.wins / s.n) * 100 }));
  }, [visible]);

  if (loading) return <div className="grid min-h-screen place-items-center bg-[#04090e] text-[13px] text-[#8ea0ad]">Loading trade journal…</div>;
  if (!trades.length) return <div className="grid min-h-screen place-items-center bg-[#04090e] text-center text-[13px] text-[#8ea0ad]"><div>{loadError ?? "No closed trades in the current database."}</div></div>;

  return (
    <div className="min-h-screen min-w-[1150px] bg-[#04090e] text-[#dce5ed]">
      <main className="px-6 py-6">
        <header className="flex items-start justify-between">
          <div>
            <h1 className="text-[21px] font-semibold">Trade Journal</h1>
            <p className="mt-1 text-[12px] text-[#8495a3]">Review closed trades to validate edge and improve.</p>
          </div>
          <div className="flex gap-2">
            <select value={coin} onChange={(e) => setCoin(e.target.value)} className="h-9 border border-[#354b59] bg-[#09141c] px-3 text-[11px] text-[#dbe5ed]">
              <option>All Coins</option>{coins.map((c) => <option key={c}>{c}</option>)}
            </select>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="h-9 border border-[#354b59] bg-[#09141c] px-3 text-[11px] text-[#dbe5ed]">
              <option>All Strategies</option>{strategies.map((s) => <option key={s}>{s}</option>)}
            </select>
            <select value={exitReason} onChange={(e) => setExitReason(e.target.value)} className="h-9 border border-[#354b59] bg-[#09141c] px-3 text-[11px] text-[#dbe5ed]">
              <option>All Exit Reasons</option>{exitReasons.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
        </header>

        <section className="mt-4 grid grid-cols-3 border border-[#1a303b] bg-[#071118]">
          <div className="border-r border-[#1a303b] px-5 py-4">
            <div className="text-[10px] font-semibold tracking-[.1em] text-[#94a5b2]">NET P&L</div>
            <div className={`mt-2 font-mono text-[20px] ${stats && stats.netPnl >= 0 ? "text-[#4de187]" : "text-[#ff5960]"}`}>{stats ? money(stats.netPnl) : "—"}</div>
          </div>
          <div className="border-r border-[#1a303b] px-5 py-4">
            <div className="text-[10px] font-semibold tracking-[.1em] text-[#94a5b2]">WIN RATE</div>
            <div className="mt-2 font-mono text-[20px] text-[#e2eaf1]">{stats ? `${stats.winRatePct.toFixed(1)}%` : "—"}</div>
            <div className="mt-1 text-[11px] text-[#8495a3]">{stats ? `${stats.wins} / ${stats.sampleSize}` : ""}</div>
          </div>
          <div className="px-5 py-4">
            <div className="text-[10px] font-semibold tracking-[.1em] text-[#94a5b2]">SAMPLE SIZE</div>
            <div className="mt-2 font-mono text-[20px] text-[#e2eaf1]">{stats?.sampleSize ?? "—"}</div>
          </div>
        </section>

        <section className="mt-4 border border-[#1a303b] bg-[#071118]">
          <div className="flex h-12 items-center justify-between border-b border-[#1a303b] px-4">
            <h2 className="text-[14px] font-medium">Closed Trades ({visible.length})</h2>
          </div>
          <div className="overflow-hidden">
            <table className="w-full border-collapse text-[11px]">
              <thead className="text-left text-[10px] text-[#8b9ca9]">
                <tr>{["Date Closed", "Coin", "Side", "Strategy", "Opened", "Entry", "Exit", "Net P&L", "Exit Reason"].map((h) => <th key={h} className="border-b border-[#1a303b] px-3 py-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {visible.map((trade) => (
                  <tr key={trade.id} onClick={() => setSelectedId(trade.id)} className={`cursor-pointer border-b border-[#182832] hover:bg-[#0d1b25] ${selected?.id === trade.id ? "bg-[#0c2237] outline outline-1 outline-[#258ee8] outline-offset-[-1px]" : ""}`}>
                    <td className="whitespace-nowrap px-3 py-3 font-mono text-[#c1ccd5]">{new Date(trade.closed_at!).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                    <td className="px-3 py-3 font-semibold">{shortSymbol(trade.symbol)}</td>
                    <td className={`px-3 py-3 font-semibold ${trade.side.toUpperCase() === "LONG" ? "text-[#40da81]" : "text-[#ff555c]"}`}>{trade.side.toUpperCase()}</td>
                    <td className="px-3 py-3 text-[#c7d2db]">{trade.strategy_name}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-[#a9b7c2]">{new Date(trade.opened_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                    <td className="px-3 py-3 font-mono">${trade.entry_price.toLocaleString()}</td>
                    <td className="px-3 py-3 font-mono">{trade.exit_price == null ? "—" : `$${trade.exit_price.toLocaleString()}`}</td>
                    <td className={`px-3 py-3 font-mono font-semibold ${(trade.pnl_usdt ?? 0) >= 0 ? "text-[#45dd84]" : "text-[#ff5960]"}`}>{money(trade.pnl_usdt)}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-[#b8c4ce]">{trade.exit_reason ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {selected && (
          <section className="mt-3 grid grid-cols-[1.05fr_1.2fr] border border-[#1a303b] bg-[#071118]">
            <div className="border-r border-[#1a303b] p-4">
              <div className="flex items-center gap-3">
                <h2 className="text-[13px] font-medium">Trade Details</h2>
                <span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${(selected.pnl_usdt ?? 0) >= 0 ? "bg-[#123927] text-[#45dc84]" : "bg-[#421d25] text-[#ff686d]"}`}>{(selected.pnl_usdt ?? 0) >= 0 ? "WIN" : "LOSS"}</span>
                {narrative?.r_multiple != null && <span className="font-mono text-[12px] text-[#47dd86]">R Result {narrative.r_multiple.toFixed(2)}R</span>}
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-y-3 text-[11px]">
                <dt className="text-[#8293a0]">Coin</dt><dd>{shortSymbol(selected.symbol)}</dd>
                <dt className="text-[#8293a0]">Side</dt><dd className={selected.side.toUpperCase() === "LONG" ? "text-[#40da81]" : "text-[#ff555c]"}>{selected.side.toUpperCase()}</dd>
                <dt className="text-[#8293a0]">Strategy</dt><dd>{selected.strategy_name}</dd>
                <dt className="text-[#8293a0]">Opened</dt><dd>{new Date(selected.opened_at).toLocaleString()}</dd>
                <dt className="text-[#8293a0]">Closed</dt><dd>{selected.closed_at ? new Date(selected.closed_at).toLocaleString() : "—"}</dd>
                <dt className="text-[#8293a0]">Held</dt><dd>{narrative?.held_duration ?? "—"}</dd>
                <dt className="text-[#8293a0]">Entry</dt><dd>${selected.entry_price.toLocaleString()}</dd>
                <dt className="text-[#8293a0]">Exit</dt><dd>{selected.exit_price == null ? "—" : `$${selected.exit_price.toLocaleString()}`}</dd>
                <dt className="text-[#8293a0]">Net P&L</dt><dd className={(selected.pnl_usdt ?? 0) >= 0 ? "text-[#45dd84]" : "text-[#ff5960]"}>{money(selected.pnl_usdt)}</dd>
              </dl>
            </div>
            <div className="grid grid-cols-2 gap-4 p-4">
              <div>
                <h3 className="text-[13px] font-medium">Entry Thesis</h3>
                <p className="mt-3 text-[11px] leading-5 text-[#c5d1db]">{narrative?.thesis_lines?.join(" ") || selected.entry_reasoning.join(" ") || "No thesis recorded."}</p>
                <h3 className="mt-6 text-[13px] font-medium text-[#ff5a61]">Invalidation</h3>
                <p className="mt-3 text-[11px] leading-5 text-[#c5d1db]">{narrative?.invalidation_line ?? "—"}</p>
              </div>
              <div>
                <h3 className="text-[13px] font-medium">Exit Reason</h3>
                <p className="mt-3 text-[11px] text-[#48dd86]">{selected.exit_reason ?? "—"}</p>
                {narrative?.lesson_line && (
                  <div className="mt-5 border border-[#583a6e] bg-[#1d1328] p-3">
                    <div className="text-[12px] font-semibold text-[#c88bff]">Lesson Observed</div>
                    <p className="mt-2 text-[10px] leading-4 text-[#c2b5cd]">{narrative.lesson_line}</p>
                  </div>
                )}
                {narrative?.failure_line && (
                  <div className="mt-3 border border-[#583a6e] bg-[#1d1328] p-3">
                    <div className="text-[12px] font-semibold text-[#ff8b8b]">What Went Wrong</div>
                    <p className="mt-2 text-[10px] leading-4 text-[#c2b5cd]">{narrative.failure_line}</p>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

        {byStrategy.length > 0 && (
          <section className="mt-3 border border-[#1a303b] bg-[#071118] p-4">
            <h2 className="text-[13px] font-medium">Strategy Comparison <span className="text-[10px] text-[#8495a3]">(current filter)</span></h2>
            <table className="mt-4 w-full border-collapse text-[11px]">
              <thead className="text-left text-[10px] text-[#8495a3]">
                <tr><th className="pb-3">Strategy</th><th className="pb-3">Net P&L</th><th className="pb-3">Win Rate</th><th className="pb-3">Trades</th></tr>
              </thead>
              <tbody>
                {byStrategy.map((row) => (
                  <tr key={row.name} className="border-t border-[#182832]">
                    <td className="py-3">{row.name}</td>
                    <td className={`py-3 font-mono ${row.pnl >= 0 ? "text-[#45dd84]" : "text-[#ff5960]"}`}>{money(row.pnl)}</td>
                    <td className="py-3 font-mono text-[#dce5ed]">{row.winRatePct.toFixed(1)}%</td>
                    <td className="py-3 font-mono text-[#dce5ed]">{row.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        <footer className="mt-3 text-[10px] text-[#778896]">All times as recorded by the server.</footer>
      </main>
    </div>
  );
}

export default function JournalPage() {
  return <AuthGate><JournalContent /></AuthGate>;
}
