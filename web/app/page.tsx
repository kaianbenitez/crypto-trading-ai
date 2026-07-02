"use client";

import { useEffect, useMemo, useState } from "react";
import NavBar from "./components/NavBar";
import { AgentStatus, api, Summary, Trade } from "@/lib/api";

const money = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const price = new Intl.NumberFormat("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 });

function serviceText(v?: string) { return !v ? "unknown" : v === "active" ? "online" : v; }
function serviceColor(v?: string) {
  if (v === "active") return "var(--green)";
  if (v === "inactive" || v === "failed") return "var(--red)";
  return "var(--muted)";
}
function pnlColor(v: number) { return v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text)"; }

function Badge({ children, color }: { children: React.ReactNode; color?: string }) {
  return (
    <span style={{ color: color || "var(--muted)", background: color ? color + "18" : "var(--surface2)", border: `1px solid ${color ? color + "30" : "var(--border)"}` }}
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium">
      {children}
    </span>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)" }} className="rounded-xl p-4">
      <div style={{ color: "var(--muted)" }} className="text-xs font-medium uppercase tracking-wider">{label}</div>
      <div style={{ color: color || "var(--text)" }} className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <div style={{ color: "var(--muted)" }} className="mt-1 text-xs">{sub}</div>}
    </div>
  );
}

function ServiceDot({ state }: { state?: string }) {
  return (
    <span className="inline-block h-2 w-2 rounded-full" style={{ background: serviceColor(state) }} />
  );
}

function OpenPosition({ trade }: { trade: Trade }) {
  return (
    <div style={{ border: "1px solid var(--border)", background: "var(--surface2)" }} className="rounded-xl p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-base">{trade.symbol}</span>
          <Badge color={trade.side === "long" ? "var(--green)" : "var(--red)"}>
            {trade.side.toUpperCase()}
          </Badge>
          <Badge>{trade.strategy_name}</Badge>
        </div>
        <Badge color="var(--amber)">OPEN</Badge>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Entry", value: price.format(trade.entry_price) },
          { label: "Stop Loss", value: price.format(trade.stop_loss) },
          { label: "Take Profit", value: price.format(trade.take_profit) },
          { label: "Leverage", value: `${trade.leverage}×` },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: "var(--surface)", border: "1px solid var(--border)" }} className="rounded-lg p-3">
            <div style={{ color: "var(--muted)" }} className="text-xs">{label}</div>
            <div className="mt-1 text-sm font-medium tabular-nums">{value}</div>
          </div>
        ))}
      </div>
      {trade.entry_reasoning[0] && (
        <div style={{ color: "var(--muted)", borderTop: "1px solid var(--border)" }} className="mt-3 pt-3 text-xs">
          {trade.entry_reasoning[0]}
        </div>
      )}
    </div>
  );
}

function TradeRow({ trade }: { trade: Trade }) {
  const pnl = trade.pnl_usdt ?? 0;
  return (
    <div style={{ borderBottom: "1px solid var(--border)" }} className="flex items-center justify-between gap-4 py-3 last:border-b-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{trade.symbol}</span>
          <Badge color={trade.side === "long" ? "var(--green)" : "var(--red)"}>{trade.side.toUpperCase()}</Badge>
          <Badge>{trade.outcome || "closed"}</Badge>
        </div>
        <div style={{ color: "var(--muted)" }} className="mt-1 text-xs truncate">
          {trade.entry_reasoning[0] || "—"}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div style={{ color: pnlColor(pnl) }} className="text-sm font-semibold tabular-nums">
          {pnl >= 0 ? "+" : ""}{money.format(pnl)} USDT
        </div>
        <div style={{ color: "var(--muted)" }} className="text-xs mt-0.5">{trade.exit_reason || "closed"}</div>
      </div>
    </div>
  );
}

function Section({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)" }} className="rounded-xl overflow-hidden">
      <div style={{ borderBottom: "1px solid var(--border)" }} className="flex items-center justify-between px-5 py-3">
        <span className="font-medium text-sm">{title}</span>
        {right}
      </div>
      <div className="px-5">{children}</div>
    </div>
  );
}

function MacroBadge({ regime }: { regime?: string }) {
  if (!regime || regime === "normal") return null;
  const colors: Record<string, string> = {
    extreme_fear: "var(--red)",
    extreme_greed: "var(--amber)",
    crowded_long: "var(--amber)",
    crowded_short: "var(--amber)",
    risk_off: "var(--red)",
  };
  const labels: Record<string, string> = {
    extreme_fear: "Extreme Fear",
    extreme_greed: "Extreme Greed",
    crowded_long: "Crowded Longs",
    crowded_short: "Crowded Shorts",
    risk_off: "Risk Off",
  };
  return <Badge color={colors[regime] || "var(--muted)"}>{labels[regime] || regime}</Badge>;
}

function DashboardContent() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [s, st, t] = await Promise.all([api.summary(), api.agentStatus(), api.trades(10)]);
      setSummary(s); setStatus(st); setTrades(t); setError(null);
    } catch { setError("Could not reach API"); }
  }

  useEffect(() => { load(); const i = setInterval(load, 15000); return () => clearInterval(i); }, []);

  async function toggleKillSwitch() {
    if (!summary) return;
    setToggling(true);
    try { await api.setKillSwitch(!summary.kill_switch_active, "manual toggle"); await load(); }
    finally { setToggling(false); }
  }

  const lastChecked = useMemo(() => {
    if (!status?.checked_at) return "—";
    return new Date(status.checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }, [status?.checked_at]);

  const openTrades = trades.filter(t => !t.closed_at);
  const closedTrades = trades.filter(t => t.closed_at);
  const killActive = summary?.kill_switch_active;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      <NavBar />
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">

        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Dashboard</h1>
            <p style={{ color: "var(--muted)" }} className="mt-1 text-sm">
              Last updated {lastChecked} · Testnet
            </p>
          </div>
          <button
            onClick={toggleKillSwitch}
            disabled={toggling}
            style={{
              background: killActive ? "rgba(239,68,68,0.12)" : "var(--surface)",
              border: `1px solid ${killActive ? "rgba(239,68,68,0.4)" : "var(--border2)"}`,
              color: killActive ? "var(--red)" : "var(--text)",
            }}
            className="rounded-lg px-4 py-2 text-sm font-medium transition-all hover:opacity-80 disabled:opacity-50"
          >
            {killActive ? "▐▐  Resume trading" : "⏹  Halt new entries"}
          </button>
        </div>

        {error && (
          <div style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)" }}
            className="mb-5 rounded-lg px-4 py-3 text-sm">{error}</div>
        )}

        {/* Stat cards */}
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard label="Agent" value={serviceText(status?.trading_agent)} color={serviceColor(status?.trading_agent)} />
          <StatCard label="Mode" value={status?.testnet ? "Testnet" : "Live"} color={status?.testnet ? "var(--amber)" : "var(--red)"} />
          <StatCard label="Bankroll" value={`$${money.format(summary?.bankroll_usdt ?? 1000)}`} sub="USDT" />
          <StatCard label="ROI" value={`${(summary?.roi_pct ?? 0) >= 0 ? "+" : ""}${(summary?.roi_pct ?? 0).toFixed(2)}%`} color={pnlColor(summary?.roi_pct ?? 0)} />
          <StatCard label="Win Rate" value={`${(summary?.win_rate_pct ?? 0).toFixed(1)}%`} sub={`${summary?.total_trades ?? 0} trades`} />
          <StatCard label="Positions" value={String(summary?.open_positions ?? 0)} color={(summary?.open_positions ?? 0) > 0 ? "var(--amber)" : "var(--text)"} />
        </div>

        {/* Middle row */}
        <div className="mb-5 grid gap-4 lg:grid-cols-3">
          {/* Services */}
          <Section title="Services">
            <div className="py-2 space-y-0">
              {[
                { name: "Trading Agent", state: status?.trading_agent },
                { name: "API Backend", state: status?.webapi },
                { name: "Dashboard", state: status?.dashboard },
                { name: "Nginx", state: status?.nginx },
              ].map(({ name, state }) => (
                <div key={name} style={{ borderBottom: "1px solid var(--border)" }} className="flex items-center justify-between py-2.5 last:border-b-0">
                  <div className="flex items-center gap-2">
                    <ServiceDot state={state} />
                    <span style={{ color: "var(--muted)" }} className="text-sm">{name}</span>
                  </div>
                  <span className="text-sm font-medium" style={{ color: serviceColor(state) }}>{serviceText(state)}</span>
                </div>
              ))}
            </div>
          </Section>

          {/* Risk */}
          <Section title="Risk">
            <div className="py-2 space-y-0">
              {[
                { label: "Risk per trade", value: "1.5%" },
                { label: "Max daily drawdown", value: "5%" },
                { label: "Default leverage", value: "3×" },
                { label: "Max positions", value: "1" },
              ].map(({ label, value }) => (
                <div key={label} style={{ borderBottom: "1px solid var(--border)" }} className="flex items-center justify-between py-2.5 last:border-b-0">
                  <span style={{ color: "var(--muted)" }} className="text-sm">{label}</span>
                  <span className="text-sm font-medium tabular-nums">{value}</span>
                </div>
              ))}
            </div>
          </Section>

          {/* Macro + Symbols */}
          <Section title="Market regime">
            <div className="py-4 space-y-4">
              <div className="flex items-center justify-between">
                <span style={{ color: "var(--muted)" }} className="text-sm">Macro</span>
                <MacroBadge regime={status?.macro_regime} />
                {(!status?.macro_regime || status.macro_regime === "normal") && (
                  <Badge color="var(--green)">Normal</Badge>
                )}
              </div>
              <div>
                <div style={{ color: "var(--muted)" }} className="text-sm mb-2">Active symbols</div>
                <div className="flex flex-wrap gap-2">
                  {(status?.symbols || ["ETH/USDT", "XRP/USDT"]).map(s => (
                    <Badge key={s} color="var(--accent)">{s.replace("/USDT", "")}</Badge>
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span style={{ color: "var(--muted)" }} className="text-sm">Kill switch</span>
                <Badge color={killActive ? "var(--red)" : "var(--green)"}>{killActive ? "ON" : "OFF"}</Badge>
              </div>
            </div>
          </Section>
        </div>

        {/* Open positions */}
        <div className="mb-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
              Open Positions
              <span className="ml-2 font-normal normal-case">{openTrades.length > 0 ? `(${openTrades.length})` : ""}</span>
            </h2>
          </div>
          {openTrades.length > 0 ? (
            <div className="space-y-3">
              {openTrades.map(t => <OpenPosition key={t.id} trade={t} />)}
            </div>
          ) : (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
              className="rounded-xl px-5 py-8 text-sm text-center">
              No active positions — bot is scanning for setups
            </div>
          )}
        </div>

        {/* Recent trades */}
        <Section
          title="Recent Closed Trades"
          right={<a href="/journal" style={{ color: "var(--accent)" }} className="text-xs hover:opacity-80">View all →</a>}
        >
          {closedTrades.length > 0 ? (
            closedTrades.map(t => <TradeRow key={t.id} trade={t} />)
          ) : (
            <div style={{ color: "var(--muted)" }} className="py-8 text-sm text-center">
              No closed trades yet
            </div>
          )}
        </Section>

      </main>
    </div>
  );
}

export default function Page() {
  return <DashboardContent />;
}
