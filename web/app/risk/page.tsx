"use client";

import { useEffect, useMemo, useState } from "react";
import { Warning } from "@phosphor-icons/react";
import { api, LivePosition, OpenPositionDetail, RiskStatus, Summary, Validation } from "@/lib/api";

function money(value: number | null | undefined) { return value == null ? "—" : `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
function pct(value: number | null | undefined) { return value == null ? "—" : `${value.toFixed(2)}%`; }
function shortSymbol(value: string) { return value.replace("/USDT:USDT", "").replace("/USDT", "").replace("USDT", ""); }

function Metric({ label, value, note, color = "text-[#dce6ed]" }: { label: string; value: string; note: string; color?: string }) {
  return (
    <div className="border-r border-[#1b303d] px-4 py-3 last:border-0">
      <div className="text-[10px] text-[#9eacb7]">{label}</div>
      <div className={`mt-2 font-mono text-[18px] ${color}`}>{value}</div>
      <div className="mt-1 text-[10px] text-[#8495a1]">{note}</div>
    </div>
  );
}

// Real bot policy thresholds (agent/config/settings.py risk_proven_*) — these
// are hardcoded server-side constants, not exposed via API, but the meaning
// is real: this is what the bot itself checks before it will scale up.
const READINESS_TARGETS: { key: string; label: string; target: string }[] = [
  { key: "min_days", label: "Minimum Trading Days", target: "30" },
  { key: "min_trades", label: "Minimum Closed Trades", target: "50" },
  { key: "expectancy", label: "Expectancy (after cost)", target: "≥ 0.10R" },
  { key: "profit_factor", label: "Profit Factor", target: "≥ 1.3" },
  { key: "drawdown", label: "Max Drawdown", target: "≤ 8.0%" },
];

export default function RiskPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [details, setDetails] = useState<OpenPositionDetail[]>([]);
  const [live, setLive] = useState<LivePosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([api.summary(), api.riskStatus(), api.validation(), api.openPositionDetails(), api.livePositions()])
      .then(([s, r, v, d, l]) => { setSummary(s); setRisk(r); setValidation(v); setDetails(d); setLive(l); setError(null); })
      .catch(() => setError("Live risk data unavailable from the backend."))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); const timer = window.setInterval(load, 10000); return () => window.clearInterval(timer); }, []);

  const bankroll = risk?.effective_bankroll_usdt ?? summary?.bankroll_usdt ?? 0;
  const portfolioRiskPct = risk?.risk_pct ?? 0;

  const rows = useMemo(() => {
    const marks = new Map(live.map((p) => [shortSymbol(p.symbol), p]));
    return details.map((item) => {
      const t = item.trade;
      const symbol = shortSymbol(t.symbol);
      const mark = marks.get(symbol);
      const riskUsdt = Math.abs(t.entry_price - t.stop_loss) * t.qty;
      const riskBankrollPct = bankroll > 0 ? (riskUsdt / bankroll) * 100 : 0;
      const notional = mark?.mark_price != null ? t.qty * mark.mark_price : null;
      return { id: t.id, symbol: t.symbol, side: t.side.toUpperCase(), riskUsdt, riskBankrollPct, notional, strategy: t.strategy_name };
    });
  }, [details, live, bankroll]);

  const totalRiskUsdt = rows.reduce((sum, r) => sum + r.riskUsdt, 0);
  const totalRiskPct = bankroll > 0 ? (totalRiskUsdt / bankroll) * 100 : 0;

  const readinessChecks = validation?.readiness.checks ?? {};
  const readinessFailed = new Set(validation?.readiness.failed ?? []);

  return (
    <div className="min-h-screen min-w-[1150px] bg-[#050b10] text-[#dce5ed]">
      <main className="flex min-h-screen flex-col">
        <header className="flex h-[72px] items-center justify-between border-b border-[#1a2b35] px-7">
          <div className="flex items-center gap-8">
            <div>
              <span className="text-[12px] text-[#a0afb9]">Bankroll Basis</span>
              <strong className="mt-2 block text-[14px]">TOTAL EQUITY</strong>
            </div>
            <div>
              <span className="text-[12px] text-[#a0afb9]">Exchange Equity</span>
              <strong className="mt-2 block font-mono text-[14px]">{money(risk?.account_equity_usdt ?? bankroll)} <small className="font-sans text-[10px]">USD</small></strong>
            </div>
          </div>
          <div>
            <span className="text-[12px] text-[#a0afb9]">Risk Tier</span>
            <strong className="mt-2 block rounded bg-[#19522e] px-2 py-1 text-[11px] text-[#74e59a]">{risk?.tier?.toUpperCase() ?? "—"}</strong>
          </div>
        </header>
        <div className="p-5">
          <div className="mb-3 flex items-center justify-between text-[10px] text-[#7f909b]">
            {loading ? "Refreshing risk data…" : "Risk state updated just now"}
            <button onClick={load} className="text-[#61b9ff]">↻ Refresh</button>
          </div>
          {error && <div className="mb-3 border border-[#765b20] bg-[#2a220f] px-3 py-2 text-[11px] text-[#eab83c]">{error}</div>}
          <section className="grid grid-cols-4 border border-[#1c303b] bg-[#0a151b]">
            <Metric label="Portfolio Risk (Amount at Risk)" value={money(totalRiskUsdt)} note={`${pct(totalRiskPct)} of bankroll`} />
            <Metric label="Current Drawdown" value={pct(risk?.drawdown_pct)} note={risk?.reason ?? "—"} />
            <Metric label="Open Positions" value={String(summary?.open_positions ?? rows.length)} note="live count" />
            <Metric label="Kill-Switch" value={summary?.kill_switch_active ? "ACTIVE ⚠" : "ARMED ◇"} note="Auto-disable at daily loss cap" color={summary?.kill_switch_active ? "text-[#ff646b]" : "text-[#49dc78]"} />
          </section>
          <section className="mt-4 border border-[#1c303b] bg-[#071119]">
            <div className="flex h-12 items-center border-b border-[#1c303b] px-4 text-[12px]">
              <span className="font-semibold">OPEN POSITIONS ({rows.length})</span>
            </div>
            <div className="overflow-hidden">
              <table className="w-full border-collapse text-[11px]">
                <thead className="bg-[#0a151c] text-left text-[9px] text-[#8fa0ad]">
                  <tr>{["COIN", "SIDE", "STRATEGY", "RISK $ (AT STOP)", "% BANKROLL", "NOTIONAL"].map((h) => <th key={h} className="border-b border-[#1b303d] px-3 py-3 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.length ? rows.map((row) => (
                    <tr key={row.id} className="border-b border-[#152832]">
                      <td className="px-3 py-3 font-mono font-semibold">{row.symbol}</td>
                      <td className={`px-3 py-3 font-semibold ${row.side === "LONG" ? "text-[#43da80]" : "text-[#ff5f68]"}`}>{row.side}</td>
                      <td className="px-3 py-3 text-[#aab8c1]">{row.strategy}</td>
                      <td className="px-3 py-3 font-mono">{money(row.riskUsdt)}</td>
                      <td className="px-3 py-3 font-mono">{pct(row.riskBankrollPct)}</td>
                      <td className="px-3 py-3 font-mono">{row.notional != null ? money(row.notional) : "—"}</td>
                    </tr>
                  )) : <tr><td colSpan={6} className="px-3 py-6 text-center text-[#7b8d99]">No open positions.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
          <section className="mt-4 border border-[#1c303b] bg-[#071119] p-4">
            <div className="mb-4 flex items-center gap-3">
              <h2 className="text-[13px] font-semibold">READINESS FOR LIVE TRADING</h2>
              <span className={`rounded px-2 py-1 text-[10px] ${validation?.readiness.ready ? "bg-[#17442a] text-[#55dd88]" : "bg-[#3a2a12] text-[#e2b33d]"}`}>{validation?.readiness.ready ? "READY" : "NOT READY"}</span>
            </div>
            <div className="grid grid-cols-[1fr_100px_100px_120px] border-b border-[#1b303d] pb-2 text-[9px] text-[#8fa0ad]">
              <span>REQUIREMENT</span><span>TARGET</span><span>CURRENT</span><span>STATUS</span>
            </div>
            {READINESS_TARGETS.map((req) => {
              const known = validation != null && req.key in readinessChecks;
              const passed = known ? readinessChecks[req.key] : null;
              const current =
                req.key === "min_days" ? String(validation?.metrics.days ?? "—") :
                req.key === "min_trades" ? String(validation?.metrics.closed_count ?? "—") :
                req.key === "expectancy" ? `${validation?.metrics.expectancy_after_estimated_cost_r?.toFixed(2) ?? "—"}R` :
                req.key === "profit_factor" ? (validation?.metrics.profit_factor?.toFixed(2) ?? "—") :
                req.key === "drawdown" ? pct(validation?.metrics.max_drawdown_pct) : "—";
              return (
                <div key={req.key} className="grid grid-cols-[1fr_100px_100px_120px] items-center border-b border-[#142630] py-3 text-[11px]">
                  <span>{req.label}</span>
                  <span className="font-mono text-[#aebbc4]">{req.target}</span>
                  <span className="font-mono text-[#aebbc4]">{current}</span>
                  <span className={passed === true ? "text-[#50dc80]" : passed === false ? "text-[#e7b538]" : "text-[#7b8d99]"}>{passed === true ? "PASS" : passed === false ? "IN PROGRESS" : "—"}</span>
                </div>
              );
            })}
          </section>
          {!validation?.readiness.ready && readinessFailed.size > 0 && (
            <section className="mt-4 border border-[#765b20] bg-[#2a220f] p-4">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold text-[#eab83c]"><Warning size={15} />Blocking readiness checks</div>
              <ul className="text-[11px] text-[#c9b98a]">{Array.from(readinessFailed).map((f) => <li key={f}>· {f}</li>)}</ul>
            </section>
          )}
        </div>
        <footer className="mt-auto flex h-9 items-center justify-between border-t border-[#1a2b35] px-7 text-[10px] text-[#778995]">
          <span>Last updated: {new Date().toISOString().slice(0, 19).replace("T", " ")} UTC</span>
          <span className="text-[#45db80]">↻ Auto-refresh: 10s</span>
        </footer>
      </main>
    </div>
  );
}
