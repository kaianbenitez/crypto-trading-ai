"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
    <span
      style={{
        color: color || "var(--muted)",
        background: color ? color + "18" : "var(--surface2)",
        border: `1px solid ${color ? color + "30" : "var(--border)"}`,
      }}
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
    >
      {children}
    </span>
  );
}

function StatCard({ label, value, sub, color, loading }: {
  label: string; value: string; sub?: string; color?: string; loading?: boolean;
}) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)" }} className="rounded-xl p-4">
      <div style={{ color: "var(--muted)" }} className="text-xs font-medium uppercase tracking-wider">{label}</div>
      {loading ? (
        <div style={{ background: "var(--border)", borderRadius: 4, width: "60%", height: 28, marginTop: 8 }} />
      ) : (
        <div style={{ color: color || "var(--text)" }} className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      )}
      {sub && !loading && <div style={{ color: "var(--muted)" }} className="mt-1 text-xs">{sub}</div>}
    </div>
  );
}

function ServiceDot({ state }: { state?: string }) {
  const label = serviceText(state);
  return (
    <span
      className="inline-block h-2 w-2 rounded-full flex-shrink-0"
      style={{ background: serviceColor(state) }}
      aria-label={label}
      role="img"
    />
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
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [confirmingHalt, setConfirmingHalt] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const confirmCancelRef = useRef<HTMLButtonElement>(null);

  async function load() {
    try {
      const [s, st, t] = await Promise.all([api.summary(), api.agentStatus(), api.trades(10)]);
      setSummary(s); setStatus(st); setTrades(t); setError(null);
    } catch {
      setError("Could not reach API — retrying every 15s");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const i = setInterval(load, 15000);
    return () => clearInterval(i);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Dismiss confirm on Escape
  useEffect(() => {
    if (!confirmingHalt) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setConfirmingHalt(false); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmingHalt]);

  async function requestHalt() {
    if (confirmingHalt) return; // already showing confirm
    setConfirmingHalt(true);
    // Move focus to cancel so Escape is natural
    setTimeout(() => confirmCancelRef.current?.focus(), 0);
  }

  async function confirmHalt() {
    setConfirmingHalt(false);
    setToggling(true);
    setToggleError(null);
    try {
      await api.setKillSwitch(true, "manual halt");
      await load();
    } catch {
      setToggleError("Halt command failed — bot may still be active. Reload and retry, or check server logs.");
    } finally {
      setToggling(false);
    }
  }

  async function resumeTrading() {
    setToggling(true);
    setToggleError(null);
    try {
      await api.setKillSwitch(false, "manual resume");
      await load();
    } catch {
      setToggleError("Resume command failed — bot may still be halted. Reload and retry, or check server logs.");
    } finally {
      setToggling(false);
    }
  }

  const lastChecked = useMemo(() => {
    if (!status?.checked_at) return "—";
    const d = new Date(status.checked_at);
    return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " +
      d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }, [status?.checked_at]);

  const openTrades = trades.filter(t => !t.closed_at);
  const closedTrades = trades.filter(t => t.closed_at);
  const killActive = summary?.kill_switch_active;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      <NavBar />

      {/* HALTED banner — dominant when kill switch is on */}
      {killActive && (
        <div
          role="status"
          aria-live="polite"
          style={{
            background: "rgba(239,68,68,0.10)",
            borderBottom: "1px solid rgba(239,68,68,0.35)",
            color: "var(--red)",
          }}
          className="px-4 py-2.5 text-sm font-medium text-center tracking-wide"
        >
          ▐▐ TRADING HALTED — all new entries blocked
        </div>
      )}

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">

        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Dashboard</h1>
            <p style={{ color: "var(--muted)" }} className="mt-1 text-sm">
              {loading ? "Connecting…" : `Last updated ${lastChecked} · Testnet`}
            </p>
          </div>

          {/* Kill switch — two-step confirm */}
          <div className="flex items-center gap-2">
            {confirmingHalt ? (
              <>
                <span style={{ color: "var(--muted)" }} className="text-sm">Confirm halt?</span>
                <button
                  onClick={confirmHalt}
                  disabled={toggling}
                  aria-label="Confirm halt — stop all new entries"
                  style={{
                    background: "rgba(239,68,68,0.15)",
                    border: "1px solid rgba(239,68,68,0.5)",
                    color: "var(--red)",
                  }}
                  className="rounded-lg px-3 py-2 text-sm font-medium hover:opacity-80 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                >
                  Yes, halt
                </button>
                <button
                  ref={confirmCancelRef}
                  onClick={() => setConfirmingHalt(false)}
                  aria-label="Cancel halt"
                  style={{ background: "var(--surface)", border: "1px solid var(--border2)", color: "var(--text)" }}
                  className="rounded-lg px-3 py-2 text-sm font-medium hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                >
                  Cancel
                </button>
              </>
            ) : killActive ? (
              <button
                onClick={resumeTrading}
                disabled={toggling}
                aria-label="Resume trading — re-enable new entries"
                aria-pressed={true}
                style={{
                  background: "rgba(239,68,68,0.12)",
                  border: "1px solid rgba(239,68,68,0.4)",
                  color: "var(--red)",
                }}
                className="rounded-lg px-4 py-2 text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                {toggling ? "Resuming…" : "▐▐  Resume trading"}
              </button>
            ) : (
              <button
                onClick={requestHalt}
                disabled={toggling || loading}
                aria-label="Halt new entries — stop the bot from opening new positions"
                aria-pressed={false}
                style={{ background: "var(--surface)", border: "1px solid var(--border2)", color: "var(--text)" }}
                className="rounded-lg px-4 py-2 text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                {toggling ? "Halting…" : "⏹  Halt new entries"}
              </button>
            )}
          </div>
        </div>

        {/* API error */}
        {error && (
          <div
            role="alert"
            aria-live="assertive"
            style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)" }}
            className="mb-5 rounded-lg px-4 py-3 text-sm flex items-center justify-between gap-4"
          >
            <span>{error}</span>
            <button
              onClick={load}
              style={{ color: "var(--red)", textDecoration: "underline", background: "none", border: "none", cursor: "pointer" }}
              className="text-sm shrink-0 hover:opacity-70"
            >
              Retry now
            </button>
          </div>
        )}

        {/* Toggle error */}
        {toggleError && (
          <div
            role="alert"
            aria-live="assertive"
            style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)" }}
            className="mb-5 rounded-lg px-4 py-3 text-sm"
          >
            {toggleError}
          </div>
        )}

        {/* Stat cards */}
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard
            label="Agent"
            value={serviceText(status?.trading_agent)}
            color={serviceColor(status?.trading_agent)}
            loading={loading}
          />
          <StatCard
            label="Mode"
            value={status?.testnet ? "Testnet" : status ? "Live" : "—"}
            color={status?.testnet ? "var(--amber)" : status ? "var(--red)" : undefined}
            loading={loading}
          />
          <StatCard
            label="Bankroll"
            value={summary ? `$${money.format(summary.bankroll_usdt)}` : "—"}
            sub="USDT"
            loading={loading}
          />
          <StatCard
            label="ROI"
            value={summary ? `${summary.roi_pct >= 0 ? "+" : ""}${summary.roi_pct.toFixed(2)}%` : "—"}
            color={summary ? pnlColor(summary.roi_pct) : undefined}
            loading={loading}
          />
          <StatCard
            label="Win Rate"
            value={summary ? `${summary.win_rate_pct.toFixed(1)}%` : "—"}
            sub={summary ? `${summary.total_trades} trades` : undefined}
            loading={loading}
          />
          <StatCard
            label="Positions"
            value={summary ? String(summary.open_positions) : "—"}
            color={summary && summary.open_positions > 0 ? "var(--amber)" : undefined}
            loading={loading}
          />
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
                {(!status?.macro_regime || status.macro_regime === "normal") ? (
                  <Badge color="var(--green)">Normal</Badge>
                ) : (
                  <MacroBadge regime={status.macro_regime} />
                )}
              </div>
              <div>
                <div style={{ color: "var(--muted)" }} className="text-sm mb-2">Active symbols</div>
                <div className="flex flex-wrap gap-2">
                  {(status?.symbols && status.symbols.length > 0 ? status.symbols : ["ETH/USDT", "XRP/USDT"]).map(s => (
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
            <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Open Positions
              {openTrades.length > 0 && (
                <span className="ml-2 font-normal" style={{ color: "var(--muted)" }}>({openTrades.length})</span>
              )}
            </h2>
          </div>
          {openTrades.length > 0 ? (
            <div className="space-y-3">
              {openTrades.map(t => <OpenPosition key={t.id} trade={t} />)}
            </div>
          ) : (
            <div
              style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
              className="rounded-xl px-5 py-8 text-sm text-center"
            >
              {loading ? "Loading positions…" : "No active positions — bot is scanning for setups"}
            </div>
          )}
        </div>

        {/* Recent trades */}
        <Section
          title="Recent Closed Trades"
          right={<a href="/journal" style={{ color: "var(--accent)" }} className="text-xs hover:opacity-80">View all →</a>}
        >
          {loading ? (
            <div style={{ color: "var(--muted)" }} className="py-8 text-sm text-center">Loading…</div>
          ) : closedTrades.length > 0 ? (
            closedTrades.map(t => <TradeRow key={t.id} trade={t} />)
          ) : (
            <div style={{ color: "var(--muted)" }} className="py-8 text-sm text-center">
              No closed trades yet
            </div>
          )}
        </Section>

      </main>

      <style>{`
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after {
            transition-duration: 0.01ms !important;
            animation-duration: 0.01ms !important;
          }
        }
      `}</style>
    </div>
  );
}

export default function Page() {
  return <DashboardContent />;
}
