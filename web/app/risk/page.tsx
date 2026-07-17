"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Warning } from "@phosphor-icons/react";
import { api, ActivityLogEntry, LivePosition, OpenPositionDetail, RiskStatus, SettingsSnapshot, Summary, Validation } from "@/lib/api";

function money(value: number | null | undefined) {
  return value == null ? "—" : `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pct(value: number | null | undefined) {
  return value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function shortSymbol(value: string) {
  return value.replace("/USDT:USDT", "").replace("/USDT", "").replace("USDT", "");
}

function settingNumber(values: Record<string, unknown> | undefined, key: string, fallback = 0) {
  const raw = values?.[key];
  const num = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(num) ? num : fallback;
}

function settingBool(values: Record<string, unknown> | undefined, key: string, fallback = false) {
  const raw = values?.[key];
  return typeof raw === "boolean" ? raw : fallback;
}

function Metric({ label, value, note, color = "text-[#dce6ed]" }: { label: string; value: string; note: string; color?: string }) {
  return (
    <div className="border-r border-[#1b303d] px-4 py-3 last:border-0">
      <div className="text-[10px] text-[#9eacb7]">{label}</div>
      <div className={`mt-2 font-mono text-[18px] ${color}`}>{value}</div>
      <div className="mt-1 text-[10px] text-[#8495a1]">{note}</div>
    </div>
  );
}

type PendingCandidate = {
  symbol: string;
  level: string;
  message: string;
  created_at: string;
};

export default function RiskPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [details, setDetails] = useState<OpenPositionDetail[]>([]);
  const [live, setLive] = useState<LivePosition[]>([]);
  const [settings, setSettings] = useState<SettingsSnapshot | null>(null);
  const [activity, setActivity] = useState<ActivityLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([api.summary(), api.riskStatus(), api.validation(), api.openPositionDetails(), api.livePositions(), api.settings(), api.activityLog(120)])
      .then(([s, r, v, d, l, cfg, log]) => {
        setSummary(s);
        setRisk(r);
        setValidation(v);
        setDetails(d);
        setLive(l);
        setSettings(cfg);
        setActivity(log);
        setError(null);
      })
      .catch(() => setError("Live risk data unavailable from the backend."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 10000);
    return () => window.clearInterval(timer);
  }, []);

  const bankroll = risk?.effective_bankroll_usdt ?? summary?.bankroll_usdt ?? 0;
  const portfolioRiskPct = risk?.risk_pct ?? 0;
  const settingsValues = settings?.values;
  const minDays = settingNumber(settingsValues, "risk_proven_min_days", validation?.validation?.min_days_required ?? 30);
  const minTrades = settingNumber(settingsValues, "risk_proven_min_trades", 50);
  const minExpectancy = settingNumber(settingsValues, "risk_proven_min_expectancy_r", 0.1);
  const minNet = settingNumber(settingsValues, "risk_proven_min_net_r_after_cost", 0.1);
  const maxDrawdown = settingNumber(settingsValues, "risk_proven_max_drawdown_pct", 8);
  const maxConcurrent = settingNumber(settingsValues, "max_concurrent_positions", 0);
  const maxPortfolioRisk = settingNumber(settingsValues, "max_portfolio_risk_pct", 0);
  const maxSameDirectionRisk = settingNumber(settingsValues, "max_same_direction_risk_pct", 0);
  const maxDailyDrawdown = settingNumber(settingsValues, "max_daily_drawdown_pct", 0);
  const riskPerTrade = settingNumber(settingsValues, "max_risk_per_trade_pct", 0);
  const validated = validation?.readiness.ready ?? false;
  const daysElapsed = validation?.validation?.days_elapsed ?? 0;
  const daysRemaining = validation?.validation?.days_remaining ?? 0;

  const rows = useMemo(() => {
    const marks = new Map(live.map((p) => [shortSymbol(p.symbol), p]));
    return details.map((item) => {
      const t = item.trade;
      const symbol = shortSymbol(t.symbol);
      const mark = marks.get(symbol);
      const riskUsdt = Math.abs(t.entry_price - t.stop_loss) * t.qty;
      const riskBankrollPct = bankroll > 0 ? (riskUsdt / bankroll) * 100 : 0;
      const notional = mark?.mark_price != null ? t.qty * mark.mark_price : null;
      return {
        id: t.id,
        symbol: t.symbol,
        side: t.side.toUpperCase(),
        strategy: t.strategy_name,
        opened_at: t.opened_at,
        riskUsdt,
        riskBankrollPct,
        notional,
        entry: t.entry_price,
        stop_loss: t.stop_loss,
        take_profit: t.take_profit,
        mark,
        reasoning: item.reasoning,
      };
    });
  }, [details, live, bankroll]);

  const pendingCandidates: PendingCandidate[] = useMemo(() => {
    const latest = new Map<string, PendingCandidate>();
    for (const entry of activity.filter((item) => item.level === "candidate" || item.level === "info")) {
      if (!entry.symbol) continue;
      const current = latest.get(entry.symbol);
      if (!current || new Date(entry.created_at).getTime() > new Date(current.created_at).getTime()) {
        latest.set(entry.symbol, {
          symbol: entry.symbol,
          level: entry.level ?? "info",
          message: entry.message,
          created_at: entry.created_at,
        });
      }
    }
    return Array.from(latest.values()).slice(0, 8);
  }, [activity]);

  const totalRiskUsdt = rows.reduce((sum, r) => sum + r.riskUsdt, 0);
  const totalRiskPct = bankroll > 0 ? (totalRiskUsdt / bankroll) * 100 : 0;
  const readinessChecks = validation?.readiness.checks ?? {};
  const readinessFailed = new Set(validation?.readiness.failed ?? []);

  return (
    <div className="min-h-screen bg-[#050b10] text-[#dce5ed]">
      <main className="px-6 py-6">
        <header className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-[22px] font-semibold">Risk</h1>
            <p className="mt-1 text-[12px] text-[#8495a3]">Live open exposure, validation floor, and risk configuration from the backend.</p>
          </div>
          <Link href="/settings" className="text-[11px] text-[#7fc7ff]">Edit live settings →</Link>
        </header>

        <div className="mb-3 mt-3 flex items-center justify-between text-[10px] text-[#7f909b]">
          {loading ? "Refreshing risk data…" : "Risk state updated just now"}
          <button onClick={load} className="text-[#61b9ff]">↻ Refresh</button>
        </div>
        {error && <div className="mb-3 border border-[#765b20] bg-[#2a220f] px-3 py-2 text-[11px] text-[#eab83c]">{error}</div>}

        <section className="grid grid-cols-5 border border-[#1c303b] bg-[#0a151b]">
          <Metric label="Portfolio Risk (Amount at Risk)" value={money(totalRiskUsdt)} note={`${pct(totalRiskPct)} of bankroll`} />
          <Metric label="Current Drawdown" value={pct(risk?.drawdown_pct)} note={risk?.reason ?? "—"} />
          <Metric label="Open Positions" value={String(summary?.open_positions ?? rows.length)} note="live count" />
          <Metric label="Validation" value={validated ? "READY" : "NOT READY"} note={`${daysElapsed}d elapsed / ${daysRemaining}d remaining`} color={validated ? "text-[#4de187]" : "text-[#eab83c]"} />
          <Metric label="Kill-Switch" value={summary?.kill_switch_active ? "ACTIVE ⚠" : "ARMED ◇"} note="Auto-disable at daily loss cap" color={summary?.kill_switch_active ? "text-[#ff646b]" : "text-[#49dc78]"} />
        </section>

        <div className="mt-4 grid grid-cols-[1.35fr_.95fr] gap-4">
          <section className="border border-[#1c303b] bg-[#071119]">
            <div className="flex h-12 items-center justify-between border-b border-[#1c303b] px-4 text-[12px]">
              <span className="font-semibold">OPEN POSITIONS ({rows.length})</span>
              <span className="text-[#7f909b]">{maxConcurrent > 0 ? `${rows.length}/${maxConcurrent} slots` : `${rows.length} open`}</span>
            </div>
            <div className="overflow-hidden">
              <table className="w-full border-collapse text-[11px]">
                <thead className="bg-[#0a151c] text-left text-[9px] text-[#8fa0ad]">
                  <tr>{["COIN", "SIDE", "STRATEGY", "OPEN", "RISK $", "% BANKROLL", "ENTRY / SL / TP", "UNREALIZED"].map((h) => <th key={h} className="border-b border-[#1b303d] px-3 py-3 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.length ? rows.map((row) => {
                    const markValue = row.mark?.unrealized_pnl ?? null;
                    return (
                      <tr key={row.id} className="border-b border-[#152832]">
                        <td className="px-3 py-3 font-mono font-semibold">{row.symbol}</td>
                        <td className={`px-3 py-3 font-semibold ${row.side === "LONG" ? "text-[#43da80]" : "text-[#ff5f68]"}`}>{row.side}</td>
                        <td className="px-3 py-3 text-[#aab8c1]">{row.strategy}</td>
                        <td className="px-3 py-3 font-mono">{new Date(row.opened_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                        <td className="px-3 py-3 font-mono">{money(row.riskUsdt)}</td>
                        <td className="px-3 py-3 font-mono">{pct(row.riskBankrollPct)}</td>
                        <td className="px-3 py-3 font-mono text-[#c6d1d9]">
                          <div>{row.entry.toLocaleString("en-US", { maximumFractionDigits: row.entry < 1 ? 6 : 2 })}</div>
                          <div className="text-[#7f909b]">SL {row.stop_loss.toLocaleString("en-US", { maximumFractionDigits: row.stop_loss < 1 ? 6 : 2 })} / TP {row.take_profit.toLocaleString("en-US", { maximumFractionDigits: row.take_profit < 1 ? 6 : 2 })}</div>
                        </td>
                        <td className={`px-3 py-3 font-mono font-semibold ${(markValue ?? 0) < 0 ? "text-[#ff5960]" : "text-[#45dd84]"}`}>{money(markValue)}</td>
                      </tr>
                    );
                  }) : <tr><td colSpan={8} className="px-3 py-6 text-center text-[#7b8d99]">No open positions.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-4">
            <div className="border border-[#1c303b] bg-[#071119] p-4">
              <h2 className="text-[13px] font-semibold">Risk configuration</h2>
              <div className="mt-4 grid grid-cols-2 gap-3 text-[11px]">
                <div><div className="text-[#8090a0]">Per-trade risk</div><div className="mt-1 font-mono">{riskPerTrade.toFixed(2)}%</div></div>
                <div><div className="text-[#8090a0]">Portfolio cap</div><div className="mt-1 font-mono">{maxPortfolioRisk.toFixed(2)}%</div></div>
                <div><div className="text-[#8090a0]">Same-dir cap</div><div className="mt-1 font-mono">{maxSameDirectionRisk.toFixed(2)}%</div></div>
                <div><div className="text-[#8090a0]">Daily drawdown</div><div className="mt-1 font-mono">{maxDailyDrawdown.toFixed(2)}%</div></div>
                <div><div className="text-[#8090a0]">Min expectancy</div><div className="mt-1 font-mono">{minExpectancy.toFixed(2)}R</div></div>
                <div><div className="text-[#8090a0]">Min net EV</div><div className="mt-1 font-mono">{minNet.toFixed(2)}R</div></div>
                <div><div className="text-[#8090a0]">Min validation days</div><div className="mt-1 font-mono">{minDays}</div></div>
                <div><div className="text-[#8090a0]">Min validation trades</div><div className="mt-1 font-mono">{minTrades}</div></div>
              </div>
              <div className="mt-4 text-[11px] text-[#8a99a4]">
                Bankroll {money(bankroll)} · leverage {settingNumber(settingsValues, "default_leverage", 1)}x / max {settingNumber(settingsValues, "max_leverage", 1)}x
              </div>
            </div>

            <div className="border border-[#1c303b] bg-[#071119] p-4">
              <h2 className="text-[13px] font-semibold">Validation floor</h2>
              <div className="mt-4 grid grid-cols-2 gap-3 text-[11px]">
                <div><div className="text-[#8090a0]">Days elapsed</div><div className="mt-1 font-mono">{daysElapsed}</div></div>
                <div><div className="text-[#8090a0]">Days remaining</div><div className="mt-1 font-mono">{daysRemaining}</div></div>
                <div><div className="text-[#8090a0]">Closed trades</div><div className="mt-1 font-mono">{validation?.metrics.closed_count ?? "—"}</div></div>
                <div><div className="text-[#8090a0]">Expectancy after cost</div><div className="mt-1 font-mono">{validation?.metrics.expectancy_after_estimated_cost_r?.toFixed(2) ?? "—"}R</div></div>
                <div><div className="text-[#8090a0]">Profit factor</div><div className="mt-1 font-mono">{validation?.metrics.profit_factor?.toFixed(2) ?? "—"}</div></div>
                <div><div className="text-[#8090a0]">Max drawdown</div><div className="mt-1 font-mono">{pct(validation?.metrics.max_drawdown_pct)}</div></div>
              </div>
              <div className="mt-4 text-[11px] text-[#8a99a4]">{validated ? "Validation has cleared the proven floor." : "Validation is still in progress and sizing should remain cautious."}</div>
            </div>

            <div className="border border-[#1c303b] bg-[#071119] p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-[13px] font-semibold">Pending candidates</h2>
                <span className="text-[10px] text-[#7f909b]">Recent candidate/info activity</span>
              </div>
              <div className="mt-3 space-y-2">
                {pendingCandidates.length ? pendingCandidates.map((item) => (
                  <div key={`${item.symbol}-${item.created_at}`} className="rounded border border-[#213443] bg-[#09131a] px-3 py-2 text-[11px]">
                    <div className="flex items-center justify-between text-[#82939f]">
                      <span>{item.symbol}</span>
                      <span className={`font-semibold ${item.level === "candidate" ? "text-[#b27aff]" : "text-[#55b8ff]"}`}>{item.level.toUpperCase()}</span>
                    </div>
                    <div className="mt-1 text-[#dbe6ef]">{item.message}</div>
                  </div>
                )) : <div className="text-[11px] text-[#7b8d99]">No pending candidate trail in the latest log window.</div>}
              </div>
            </div>
          </section>
        </div>

        {(!validation?.readiness.ready && readinessFailed.size > 0) && (
          <section className="mt-4 border border-[#765b20] bg-[#2a220f] p-4">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold text-[#eab83c]"><Warning size={15} />Blocking readiness checks</div>
            <ul className="text-[11px] text-[#c9b98a]">{Array.from(readinessFailed).map((f) => <li key={f}>• {f}</li>)}</ul>
          </section>
        )}

        <footer className="mt-4 flex items-center justify-between text-[10px] text-[#778896]">
          <span>Live settings are pulled from the backend on each refresh.</span>
          <span className="text-[#45db80]">↻ Auto-refresh: 10s</span>
        </footer>
      </main>
    </div>
  );
}
