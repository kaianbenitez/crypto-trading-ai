"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Play, Prohibit, ArrowSquareOut, WarningCircle } from "@phosphor-icons/react";
import { AgentStatus, api, CandlePayload, LivePosition, OpenPositionDetail, Summary, Trade } from "@/lib/api";
import { money, pct, pnlColor, price4 } from "@/lib/format";
import AuthGate from "./components/AuthGate";
import Sidebar from "./components/Sidebar";
import CoinLogo from "./components/CoinLogo";
import { Card, Badge, Button, StatCard } from "./components/ui";

// TradingView chart link for a symbol, opened in a new tab from the coin logo/name.
function tradingViewUrl(symbol: string) {
  const base = symbol.split("/")[0].toUpperCase();
  return `https://www.tradingview.com/chart/?symbol=BINANCE%3A${base}USDT.P`;
}

const REGIME_META: Record<string, { label: string; color: string }> = {
  extreme_fear:  { label: "Extreme Fear",    color: "var(--red)"   },
  extreme_greed: { label: "Extreme Greed",   color: "var(--amber)" },
  crowded_long:  { label: "Crowded Longs",   color: "var(--amber)" },
  crowded_short: { label: "Crowded Shorts",  color: "var(--amber)" },
  risk_off:      { label: "Risk Off",        color: "var(--red)"   },
  normal:        { label: "Normal",          color: "var(--green)" },
};

// Plain-language labels for raw strategy/regime codes still sent as short tags.
const STRATEGY_LABEL: Record<string, string> = {
  trend_following: "Trend-following",
  mean_reversion: "Bounce (mean-reversion)",
  volatility_filter: "Standing aside",
};
const TRADE_REGIME_LABEL: Record<string, string> = {
  trending: "Trending",
  ranging: "Sideways",
  high_vol: "Volatile",
};
function friendlyStrategy(s?: string) { return s ? (STRATEGY_LABEL[s] ?? s.replace(/_/g, " ")) : "—"; }
function friendlyTradeRegime(r?: string) { return r ? (TRADE_REGIME_LABEL[r] ?? r.replace(/_/g, " ")) : "—"; }

function parseApiDate(value: string) {
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  return new Date(normalized.endsWith("Z") || normalized.includes("+") ? normalized : normalized + "Z");
}

function openDuration(openedAt: string) {
  const opened = parseApiDate(openedAt).getTime();
  if (!Number.isFinite(opened)) return "Open";
  const totalMinutes = Math.max(0, Math.floor((Date.now() - opened) / 60000));
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;

  if (days > 0) return `${days}d ${hours}h open`;
  if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, "0")}m open`;
  return `${Math.max(1, minutes)}m open`;
}

// ── PnlBar: visual range bar for entry/SL/TP ────────────────────────────────
function PnlBar({ trade, currentPrice, tall = false }: { trade: Pick<Trade, "entry_price" | "stop_loss" | "take_profit" | "side">; currentPrice?: number; tall?: boolean }) {
  const { entry_price, stop_loss, take_profit, side } = trade;
  const lo = Math.min(entry_price, stop_loss, take_profit, currentPrice ?? entry_price);
  const hi = Math.max(entry_price, stop_loss, take_profit, currentPrice ?? entry_price);
  const span = hi - lo || 1;
  const pos  = (v: number) => `${((v - lo) / span) * 100}%`;

  return (
    <div style={{ position: "relative", height: tall ? 10 : 6, background: "var(--surface3)", borderRadius: 4, margin: tall ? "12px 0 14px" : "12px 0 4px" }}>
      {/* SL zone */}
      {side === "long" ? (
        <div style={{ position: "absolute", left: pos(stop_loss), right: `${100 - parseFloat(pos(entry_price))}%`, height: "100%", background: "var(--red)", opacity: 0.35, borderRadius: 3 }} />
      ) : (
        <div style={{ position: "absolute", left: pos(entry_price), right: `${100 - parseFloat(pos(stop_loss))}%`, height: "100%", background: "var(--red)", opacity: 0.35, borderRadius: 3 }} />
      )}
      {/* TP zone */}
      {side === "long" ? (
        <div style={{ position: "absolute", left: pos(entry_price), right: `${100 - parseFloat(pos(take_profit))}%`, height: "100%", background: "var(--green)", opacity: 0.35, borderRadius: 3 }} />
      ) : (
        <div style={{ position: "absolute", left: pos(take_profit), right: `${100 - parseFloat(pos(entry_price))}%`, height: "100%", background: "var(--green)", opacity: 0.35, borderRadius: 3 }} />
      )}
      {/* Markers */}
      {[
        { price: stop_loss,   color: "var(--red)",   label: "SL" },
        { price: entry_price, color: "var(--accent)", label: "E"  },
        { price: take_profit, color: "var(--green)",  label: "TP" },
      ].map(({ price: p, color: c, label }) => (
        <div key={label} style={{ position: "absolute", left: pos(p), transform: "translateX(-50%)", top: -3, width: 12, height: 12, borderRadius: "50%", background: c, border: "2px solid var(--surface)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2 }} title={`${label}: ${price4.format(p)}`} />
      ))}
      {currentPrice !== undefined && (
        <div
          style={{ position: "absolute", left: pos(currentPrice), transform: "translateX(-50%)", top: tall ? -6 : -5, width: tall ? 2 : 10, height: tall ? 22 : 16, borderRadius: 2, background: "var(--text)", boxShadow: "0 0 0 2px var(--surface)", zIndex: 3 }}
          title={`Current: ${price4.format(currentPrice)}`}
        />
      )}
    </div>
  );
}

// ── open position card ───────────────────────────────────────────────────────
function latestClose(payload?: CandlePayload) {
  const last = payload?.candles?.[payload.candles.length - 1];
  return last?.close;
}

function unrealizedPct(trade: Pick<Trade, "side" | "entry_price">, currentPrice?: number) {
  if (currentPrice === undefined || !trade.entry_price) return undefined;
  const direction = trade.side === "long" ? 1 : -1;
  return ((currentPrice - trade.entry_price) / trade.entry_price) * direction * 100;
}

// One canonical open-position card. `detail` (the enriched reasoning payload)
// is optional — when it's missing (API hiccup, or this trade just isn't in
// that response yet) the card falls back to the plain trade fields instead
// of swapping to a structurally different layout. Same shape either way.
function OpenPositionCard({ trade, detail, payload, live }: { trade: Trade; detail?: OpenPositionDetail; payload?: CandlePayload; live?: LivePosition }) {
  const sideColor = trade.side === "long" ? "var(--green)" : "var(--red)";
  // Prefer the exchange's own mark price / unrealized PnL / ROI — they account
  // for trading fees and break-even price, unlike the (close - entry) * qty
  // approximation from 1h candles, which was drifting a few dollars off.
  const currentPrice = live?.mark_price ?? latestClose(payload);
  const openPct = live?.roi_pct ?? unrealizedPct(trade, currentPrice);
  // Show every reason the agent gathered, not just the first — a single
  // line was always the same generic regime restatement on every trade.
  const note = detail ? detail.reasoning.thesis.join(" ") : specificReasoning(trade.entry_reasoning);
  const snapshot = trade.indicator_snapshot as Record<string, unknown> | undefined;
  const riskPct = typeof snapshot?.actual_risk_pct === "number" ? snapshot.actual_risk_pct : undefined;

  return (
    <div className="ui-card" style={{ borderColor: `color-mix(in oklab, ${sideColor} 22%, var(--border))` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "12px 14px", borderBottom: "1px solid var(--border)", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          <a
            href={tradingViewUrl(trade.symbol)}
            target="_blank"
            rel="noopener noreferrer"
            title={`Open ${trade.symbol} chart on TradingView`}
            style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "inherit" }}
          >
            <CoinLogo symbol={trade.symbol} size={26} />
            <div>
              <div style={{ fontWeight: 700, fontSize: "var(--text-base)" }}>{trade.symbol}</div>
              <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>{friendlyStrategy(trade.strategy_name)} · {friendlyTradeRegime(trade.regime)}</div>
            </div>
          </a>
          <Badge color={sideColor}>{trade.side.toUpperCase()}</Badge>
        </div>
        <span style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>
          {openDuration(trade.opened_at)}
        </span>
      </div>

      <div style={{ padding: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginBottom: 3 }}>Unrealized P&L</div>
            <div style={{ color: openPct === undefined ? "var(--muted)" : pnlColor(openPct), fontSize: "var(--text-2xl)", fontWeight: 750, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
              {openPct === undefined ? "n/a" : `${openPct >= 0 ? "+" : ""}${openPct.toFixed(2)}%`}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginBottom: 3 }}>Price now</div>
            <div style={{ fontSize: "var(--text-md)", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{currentPrice === undefined ? "..." : price4.format(currentPrice)}</div>
          </div>
        </div>

        <PnlBar trade={trade} currentPrice={currentPrice} tall />

        <div
          style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginBottom: 8 }}
          title={riskPct !== undefined ? `${riskPct.toFixed(2)}% of bankroll risked · qty ${price4.format(trade.qty)} · ${trade.leverage}× leverage` : undefined}
        >
          <span style={{ color: "var(--red)" }}>SL {price4.format(trade.stop_loss)}</span>
          {" · "}
          <span style={{ color: "var(--accent)" }}>Entry {price4.format(trade.entry_price)}</span>
          {" · "}
          <span style={{ color: "var(--green)" }}>TP {price4.format(trade.take_profit)}</span>
        </div>

        {detail?.reasoning.weakness && (
          <div style={{ color: "var(--amber)", fontSize: "var(--text-2xs)", lineHeight: 1.4, display: "flex", gap: 4, alignItems: "flex-start", marginBottom: note ? 8 : 0 }}>
            <WarningCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} /> {detail.reasoning.weakness}
          </div>
        )}

        {note && (
          <details style={{ paddingTop: 8, borderTop: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
              <span style={{ background: "var(--surface2)", borderRadius: "var(--radius-sm)", padding: "3px 8px", fontSize: "var(--text-2xs)", color: "var(--muted)" }}>
                ⚙️ {friendlyStrategy(trade.strategy_name)}
              </span>
              <span style={{ background: "var(--surface2)", borderRadius: "var(--radius-sm)", padding: "3px 8px", fontSize: "var(--text-2xs)", color: "var(--muted)" }}>
                📈 {friendlyTradeRegime(trade.regime)}
              </span>
            </div>
            <summary className="reasoning-toggle" style={{ cursor: "pointer", color: "var(--accent)", fontSize: "var(--text-2xs)", fontWeight: 700, letterSpacing: "0.02em" }}>
              View Full Trade Thesis
            </summary>
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6, background: "var(--surface2)", borderRadius: "var(--radius-sm)", padding: 10 }}>
              <div style={{ color: "var(--text)", fontSize: "var(--text-xs)", lineHeight: 1.45 }}>
                {note}
              </div>
              {detail && detail.reasoning.why_accepted.length > 0 && (
                <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", lineHeight: 1.4 }}>
                  Why accepted: {detail.reasoning.why_accepted.join(" ")}
                </div>
              )}
              {detail && (
                <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", lineHeight: 1.4 }}>
                  Invalidation: {detail.reasoning.invalidation}
                </div>
              )}
              {detail?.reasoning.past_context && (
                <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", lineHeight: 1.4 }}>
                  Past: {detail.reasoning.past_context}
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

// Exit reasons that are obvious from the win/loss color + amount already
// shown — no need to spell them out. Anything else (trailing exits, manual
// fixes, forced closes) is genuinely useful context, so it's kept.
const OBVIOUS_EXIT_REASONS = new Set(["take_profit", "stop_loss"]);
const EXIT_REASON_LABEL: Record<string, string> = {
  trailing_take_profit: "Trailing stop locked in the win",
  trailing_stop: "Trailing stop hit (had moved from entry)",
  max_hold_timeout: "Force-closed after max hold time",
  manual_reconcile_duplicate: "Closed manually (duplicate fix)",
};
function noteworthyExitReason(reason: string | null): string | null {
  if (!reason || OBVIOUS_EXIT_REASONS.has(reason)) return null;
  return EXIT_REASON_LABEL[reason] ?? reason.replace(/_/g, " ");
}

// Every trade's reasoning always starts with the same generic market-read
// restatement (it's already shown as the strategy/regime badge) — pick the
// first line that's actually specific to this trade instead, so cards don't
// all read identically.
function specificReasoning(lines: string[]): string {
  return lines.find(l => !l.startsWith("Market read:")) ?? lines[0] ?? "—";
}

// ── trade card (compact, used in a responsive grid instead of full-width rows) ─
function TradeRow({ trade }: { trade: Trade }) {
  const pnl = trade.pnl_usdt ?? 0;
  const sideColor = trade.side === "long" ? "var(--green)" : "var(--red)";
  const pnlPct = trade.exit_price !== null ? unrealizedPct(trade, trade.exit_price) : undefined;
  const footerNote = noteworthyExitReason(trade.exit_reason) ?? specificReasoning(trade.entry_reasoning);
  return (
    <Link
      href={`/journal?trade=${trade.id}`}
      className="ui-card ui-card--hoverable"
      style={{ color: "inherit", textDecoration: "none", background: "var(--surface2)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <CoinLogo symbol={trade.symbol} size={20} />
        <span style={{ fontWeight: 600, fontSize: "var(--text-sm)", flex: 1, minWidth: 0 }}>{trade.symbol.replace("/USDT", "")}</span>
        <Badge color={sideColor}>{trade.side.toUpperCase()}</Badge>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ color: pnlColor(pnl), fontWeight: 700, fontSize: "var(--text-md)", fontVariantNumeric: "tabular-nums" }}>
            {pnlPct !== undefined ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%` : "—"}
          </span>
        </div>
        <span style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>
          {trade.closed_at ? parseApiDate(trade.closed_at).toLocaleDateString([], { month: "short", day: "numeric" }) : "—"}
        </span>
      </div>
      <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {footerNote}
      </div>
    </Link>
  );
}

// ── kill switch button ───────────────────────────────────────────────────────
function KillSwitchButton({ killActive, toggling, confirming, onHalt, onConfirm, onCancel, onResume, cancelRef }: {
  killActive?: boolean; toggling: boolean; confirming: boolean;
  onHalt: () => void; onConfirm: () => void; onCancel: () => void; onResume: () => void;
  cancelRef: React.RefObject<HTMLButtonElement | null>;
}) {
  if (confirming) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <span style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>Confirm halt?</span>
      <Button variant="danger" onClick={onConfirm} disabled={toggling} aria-label="Confirm halt" style={{ minHeight: 44 }}>
        Yes, halt
      </Button>
      <Button ref={cancelRef} variant="secondary" onClick={onCancel} aria-label="Cancel" style={{ minHeight: 44 }}>
        Cancel
      </Button>
    </div>
  );

  if (killActive) return (
    <Button variant="danger" onClick={onResume} disabled={toggling} aria-label="Resume trading" style={{ minHeight: 44, padding: "0 18px" }}>
      <Play size={14} weight="fill" /> {toggling ? "Resuming…" : "Resume trading"}
    </Button>
  );

  return (
    <Button variant="secondary" onClick={onHalt} disabled={toggling} aria-label="Halt new entries" style={{ minHeight: 44, padding: "0 18px" }}>
      <Prohibit size={14} style={{ color: "var(--red)" }} />
      {toggling ? "Halting…" : "Halt entries"}
    </Button>
  );
}

// ── main dashboard ───────────────────────────────────────────────────────────
function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [status,  setStatus]  = useState<AgentStatus | null>(null);
  const [trades,  setTrades]  = useState<Trade[]>([]);
  const [positionDetails, setPositionDetails] = useState<OpenPositionDetail[]>([]);
  const [candlePayloads, setCandlePayloads] = useState<Record<string, CandlePayload>>({});
  const [livePositions, setLivePositions] = useState<Record<string, LivePosition>>({});
  const [loading, setLoading] = useState(true);
  const [toggling,      setToggling]      = useState(false);
  const [confirmingHalt,setConfirmingHalt]= useState(false);
  const [error,         setError]         = useState<string | null>(null);
  const [toggleError,   setToggleError]   = useState<string | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  async function load() {
    try {
      const [s, st, t, details, live] = await Promise.all([
        api.summary(),
        api.agentStatus(),
        api.trades(15),
        api.openPositionDetails(),
        api.livePositions().catch(() => []),
      ]);
      setSummary(s); setStatus(st); setTrades(t); setPositionDetails(details); setError(null);
      const liveBySymbol: Record<string, LivePosition> = {};
      live.forEach(p => {
        const norm = p.symbol.includes("/") ? p.symbol : p.symbol.replace(/USDT$/, "/USDT");
        liveBySymbol[norm] = p;
      });
      setLivePositions(liveBySymbol);
      if (details.length > 0) {
        const candles = await Promise.all(
          details.map(d => api.candles(d.trade.symbol, "1h", 120).catch(() => null))
        );
        const nextPayloads: Record<string, CandlePayload> = {};
        candles.forEach((payload, idx) => {
          if (payload) nextPayloads[details[idx].trade.symbol] = payload;
        });
        setCandlePayloads(nextPayloads);
      } else {
        setCandlePayloads({});
      }
    } catch {
      setError("Cannot reach API — retrying every 15 s");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!confirmingHalt) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setConfirmingHalt(false); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmingHalt]);

  async function confirmHalt() {
    setConfirmingHalt(false); setToggling(true); setToggleError(null);
    try { await api.setKillSwitch(true, "manual halt"); await load(); }
    catch { setToggleError("Halt failed — check server logs."); }
    finally { setToggling(false); }
  }

  async function resumeTrading() {
    setToggling(true); setToggleError(null);
    try { await api.setKillSwitch(false, "manual resume"); await load(); }
    catch { setToggleError("Resume failed — check server logs."); }
    finally { setToggling(false); }
  }

  const lastChecked = useMemo(() => {
    if (!status?.checked_at) return "—";
    const d = parseApiDate(status.checked_at);
    return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " +
           d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }, [status?.checked_at]);

  const openTrades   = trades.filter(t => !t.closed_at);
  const openCount    = openTrades.length;
  const closedTrades = trades.filter(t =>  t.closed_at);
  const detailByTradeId = useMemo(() => {
    const map: Record<number, OpenPositionDetail> = {};
    positionDetails.forEach(d => { map[d.trade.id] = d; });
    return map;
  }, [positionDetails]);
  const killActive   = summary?.kill_switch_active;
  const regime       = status?.macro_regime || "normal";
  const regimeMeta   = REGIME_META[regime] || { label: regime, color: "var(--muted)" };

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", display: "flex" }}>
      <Sidebar />
      <div style={{ flex: 1, minWidth: 0 }}>

      {/* HALTED banner */}
      {killActive && (
        <div role="status" aria-live="polite"
          style={{ background: "color-mix(in oklab, var(--red) 10%, transparent)", borderBottom: "1px solid color-mix(in oklab, var(--red) 30%, transparent)", color: "var(--red)", padding: "9px 24px", fontSize: "var(--text-xs)", fontWeight: 600, textAlign: "center", letterSpacing: "0.05em" }}>
          ▐▐ TRADING HALTED — all new entries blocked
        </div>
      )}

      <main className="page-main" style={{ maxWidth: 1560, margin: "0 auto" }}>

        {/* Header row */}
        <div className="header-row" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h1 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0 }}>Dashboard</h1>
              {killActive && <Badge color="var(--red)">HALTED</Badge>}
            </div>
            <p style={{ color: "var(--muted)", fontSize: "var(--text-xs)", margin: "4px 0 0" }}>
              {loading ? "Connecting…" : `Updated ${lastChecked}`}
            </p>
          </div>
          <KillSwitchButton
            killActive={killActive}
            toggling={toggling}
            confirming={confirmingHalt}
            onHalt={() => { setConfirmingHalt(true); setTimeout(() => cancelRef.current?.focus(), 0); }}
            onConfirm={confirmHalt}
            onCancel={() => setConfirmingHalt(false)}
            onResume={resumeTrading}
            cancelRef={cancelRef}
          />
        </div>

        {/* Errors */}
        {error && (
          <div role="alert" style={{ background: "color-mix(in oklab, var(--red) 8%, transparent)", border: "1px solid color-mix(in oklab, var(--red) 30%, transparent)", color: "var(--red)", borderRadius: "var(--radius-sm)", padding: "10px 16px", fontSize: "var(--text-xs)", marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <span>{error}</span>
            <button onClick={load} className="ui-btn ui-btn--ghost" style={{ color: "var(--red)", textDecoration: "underline" }}>Retry</button>
          </div>
        )}
        {toggleError && (
          <div role="alert" style={{ background: "color-mix(in oklab, var(--red) 8%, transparent)", border: "1px solid color-mix(in oklab, var(--red) 30%, transparent)", color: "var(--red)", borderRadius: "var(--radius-sm)", padding: "10px 16px", fontSize: "var(--text-xs)", marginBottom: 16 }}>
            {toggleError}
          </div>
        )}

        {/* Stat row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 18 }}>
          {[
            <StatCard key="bankroll" label="Bankroll" value={summary ? `$${money.format(summary.bankroll_usdt)}` : "—"} sub="USDT balance" loading={loading} accent="var(--accent)" />,
            <StatCard key="roi" label="ROI" value={summary ? pct(summary.roi_pct) : "—"} color={summary ? pnlColor(summary.roi_pct) : undefined} sub={summary ? `${summary.total_trades} closed trades, all-time` : "all-time"} loading={loading} accent={summary ? pnlColor(summary.roi_pct) : undefined} />,
            <StatCard key="winrate" label="Win Rate" value={summary ? `${summary.win_rate_pct.toFixed(1)}%` : "—"} sub={summary ? `${summary.total_trades} total` : undefined} loading={loading} accent={summary ? (summary.win_rate_pct >= 50 ? "var(--green)" : "var(--amber)") : undefined} />,
            <StatCard key="open" label="Open" value={summary ? String(summary.open_positions) : "—"} color={summary && summary.open_positions > 0 ? "var(--amber)" : undefined} sub="positions" loading={loading} accent={summary && summary.open_positions > 0 ? "var(--amber)" : undefined} />,
            <StatCard key="macro" label="Macro" value={regimeMeta.label} color={regime === "normal" ? undefined : regimeMeta.color} sub={`size ×${status ? (status as AgentStatus & { size_multiplier?: number }).size_multiplier?.toFixed(2) ?? "—" : "—"}`} loading={loading} accent={regime === "normal" ? "var(--border2)" : regimeMeta.color} />,
          ].map((el, i) => (
            <div key={el.key} className="rise-in" style={{ animationDelay: `${i * 40}ms` }}>{el}</div>
          ))}
        </div>

        {/* Open positions */}
        <div style={{ marginBottom: 18 }}>
          <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <h2 style={{ fontSize: "var(--text-xs)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", margin: 0 }}>Open Positions</h2>
            {openCount > 0 && <Badge color="var(--amber)">{openCount}</Badge>}
          </div>
          {openTrades.length > 0 ? (
            <div className="open-position-list" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 10 }}>
              {openTrades.map(t => (
                <OpenPositionCard
                  key={t.id}
                  trade={t}
                  detail={detailByTradeId[t.id]}
                  payload={candlePayloads[t.symbol]}
                  live={livePositions[t.symbol]}
                />
              ))}
            </div>
          ) : (
            <div className="ui-card" style={{ minHeight: 90, padding: 16, color: "var(--muted)", fontSize: "var(--text-sm)", display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center" }}>
              {loading ? "Loading positions..." : "No open position right now — the agent is scanning every active coin and will open one once a good setup shows up."}
            </div>
          )}
        </div>

        {/* Recent closed trades */}
        <Card title="Recent Closed Trades" right={<Link href="/journal" style={{ color: "var(--accent)", fontSize: "var(--text-2xs)", textDecoration: "none", display: "flex", alignItems: "center", gap: 3 }}>View all <ArrowSquareOut size={11} /></Link>} noPad>
          <div style={{ padding: "12px 20px 16px" }}>
            {loading ? (
              <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: "var(--text-sm)" }}>Loading…</div>
            ) : closedTrades.length > 0 ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
                {closedTrades.map(t => <TradeRow key={t.id} trade={t} />)}
              </div>
            ) : (
              <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: "var(--text-sm)" }}>No closed trades yet</div>
            )}
          </div>
        </Card>

      </main>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <Dashboard />
    </AuthGate>
  );
}
