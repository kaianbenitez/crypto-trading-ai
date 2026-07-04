"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AgentStatus, api, CandlePayload, CoinDigest, LivePosition, OpenPositionDetail, Summary, Trade } from "@/lib/api";
import { money, pct, pnlColor, price4 } from "@/lib/format";
import AuthGate from "./components/AuthGate";
import Sidebar from "./components/Sidebar";
import CoinLogo from "./components/CoinLogo";
import CoinDigestCard from "./components/CoinDigestCard";

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

// ── primitives ───────────────────────────────────────────────────────────────
function Badge({ children, color, bg }: { children: React.ReactNode; color?: string; bg?: string }) {
  const c = color || "var(--muted)";
  return (
    <span style={{ color: c, background: bg || c + "18", border: `1px solid ${c}30`, borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 600, letterSpacing: "0.03em", display: "inline-flex", alignItems: "center", gap: 4, whiteSpace: "nowrap" }}>
      {children}
    </span>
  );
}

function Skeleton({ w, h }: { w?: string; h?: number }) {
  return <span className="skeleton" style={{ display: "block", width: w || "60%", height: h || 20 }} />;
}

// ── stat card ────────────────────────────────────────────────────────────────
function StatCard({
  label, value, sub, color, loading, accent, large
}: {
  label: string; value: string; sub?: string; color?: string; loading?: boolean; accent?: string; large?: boolean;
}) {
  return (
    <div style={{
      background: accent
        ? `linear-gradient(135deg, ${accent}55 0%, ${accent}22 55%, ${accent}0f 100%)`
        : "var(--surface)",
      border: `1px solid ${accent ? accent + "60" : "var(--border)"}`,
      borderRadius: 14,
      padding: large ? "20px 20px" : "14px 16px",
      position: "relative",
      overflow: "hidden",
    }}>
      {accent && <span style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: accent, borderRadius: "14px 14px 0 0" }} />}
      <div style={{ color: "var(--muted)", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</div>
      {loading ? (
        <Skeleton h={large ? 32 : 24} />
      ) : (
        <div style={{ color: color || "var(--text)", fontSize: large ? 26 : 20, fontWeight: 700, marginTop: 6, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>{value}</div>
      )}
      {sub && !loading && <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  );
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

function unrealizedPnl(trade: Pick<Trade, "side" | "entry_price" | "qty">, currentPrice?: number) {
  if (currentPrice === undefined) return undefined;
  const direction = trade.side === "long" ? 1 : -1;
  return (currentPrice - trade.entry_price) * direction * trade.qty;
}

function unrealizedPct(trade: Pick<Trade, "side" | "entry_price">, currentPrice?: number) {
  if (currentPrice === undefined || !trade.entry_price) return undefined;
  const direction = trade.side === "long" ? 1 : -1;
  return ((currentPrice - trade.entry_price) / trade.entry_price) * direction * 100;
}

function DetailedOpenPosition({ detail, payload, live }: { detail: OpenPositionDetail; payload?: CandlePayload; live?: LivePosition }) {
  const trade = detail.trade;
  const sideColor = trade.side === "long" ? "var(--green)" : "var(--red)";
  // Prefer the exchange's own mark price / unrealized PnL / ROI — they account
  // for trading fees and break-even price, unlike the (close - entry) * qty
  // approximation from 1h candles, which was drifting a few dollars off.
  const currentPrice = live?.mark_price ?? latestClose(payload);
  const openPnl = live?.unrealized_pnl ?? unrealizedPnl(trade, currentPrice);
  const openPct = live?.roi_pct ?? unrealizedPct(trade, currentPrice);
  // Show every reason the agent gathered, not just the first — a single
  // line was always the same generic regime restatement on every trade.
  const note = detail.reasoning.thesis.join(" ");
  const snapshot = trade.indicator_snapshot as Record<string, unknown> | undefined;
  const riskedAmt = typeof snapshot?.actual_risk_usdt === "number"
    ? snapshot.actual_risk_usdt
    : Math.abs(trade.entry_price - trade.stop_loss) * trade.qty;

  return (
    <div style={{ background: "var(--surface)", border: `1px solid ${sideColor}24`, borderRadius: 10, overflow: "hidden" }}>
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
              <div style={{ fontWeight: 700, fontSize: 14 }}>{trade.symbol}</div>
              <div style={{ color: "var(--muted)", fontSize: 11 }}>{friendlyStrategy(trade.strategy_name)} · {friendlyTradeRegime(trade.regime)}</div>
            </div>
          </a>
          <Badge color={sideColor}>{trade.side.toUpperCase()}</Badge>
        </div>
        <span style={{ color: "var(--muted)", fontSize: 11 }}>
          Opened {new Date(trade.opened_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>

      <div style={{ padding: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 3 }}>Unrealized P&L</div>
            <div style={{ color: openPnl === undefined ? "var(--muted)" : pnlColor(openPnl), fontSize: 24, fontWeight: 750, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
              {openPnl === undefined ? "Loading" : `${openPnl >= 0 ? "+" : ""}$${money.format(openPnl)}`}
            </div>
            {openPct !== undefined && (
              <div style={{ color: pnlColor(openPct), fontSize: 12, marginTop: 5 }}>
                {openPct >= 0 ? "+" : ""}{openPct.toFixed(2)}% since entry
              </div>
            )}
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 3 }}>Price now</div>
            <div style={{ fontSize: 16, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{currentPrice === undefined ? "..." : price4.format(currentPrice)}</div>
          </div>
        </div>

        <PnlBar trade={trade} currentPrice={currentPrice} tall />

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 6 }}>
          {[
            ["Stop Loss", price4.format(trade.stop_loss), "var(--red)"],
            ["Entry", price4.format(trade.entry_price), "var(--accent)"],
            ["Take Profit", price4.format(trade.take_profit), "var(--green)"],
          ].map(([label, value, color]) => (
            <div key={label} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "7px 9px" }}>
              <div style={{ color: color as string, fontSize: 11, fontWeight: 700 }}>{label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums", marginTop: 3 }}>{value}</div>
            </div>
          ))}
        </div>

        <div style={{ color: "var(--muted)", fontSize: 10.5, marginBottom: note ? 10 : 0 }}>
          ${money.format(riskedAmt)} at risk · qty {price4.format(trade.qty)}
        </div>

        {note && (
          <div style={{ paddingTop: 8, borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 6 }}>
            <div>
              <div style={{ color: "var(--muted)", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 3 }}>
                Thesis
              </div>
              <div style={{ color: "var(--text)", fontSize: 11.5, lineHeight: 1.45 }}>
                {note}
              </div>
            </div>
            {detail.reasoning.concern && (
              <div style={{ color: "var(--amber)", fontSize: 11, lineHeight: 1.4 }}>
                ⚠ Concern: {detail.reasoning.concern}
              </div>
            )}
            <div style={{ color: "var(--muted)", fontSize: 11, lineHeight: 1.4 }}>
              Invalidation: {detail.reasoning.invalidation}
            </div>
            {detail.reasoning.past_context && (
              <div style={{ color: "var(--muted)", fontSize: 11, lineHeight: 1.4 }}>
                Past: {detail.reasoning.past_context}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function OpenPosition({ trade }: { trade: Trade }) {
  const sideColor = trade.side === "long" ? "var(--green)" : "var(--red)";
  const snapshot = trade.indicator_snapshot as Record<string, unknown> | undefined;
  const riskedAmt = typeof snapshot?.actual_risk_usdt === "number"
    ? snapshot.actual_risk_usdt
    : Math.abs(trade.entry_price - trade.stop_loss) * trade.qty;
  return (
    <div style={{ background: "var(--surface)", border: `1px solid ${sideColor}22`, borderRadius: 14, padding: "16px 20px", position: "relative", overflow: "hidden" }}>
      <span style={{ position: "absolute", top: 0, left: 0, bottom: 0, width: 3, background: sideColor, borderRadius: "14px 0 0 14px" }} />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <a
          href={tradingViewUrl(trade.symbol)}
          target="_blank"
          rel="noopener noreferrer"
          title={`Open ${trade.symbol} chart on TradingView`}
          style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "inherit" }}
        >
          <CoinLogo symbol={trade.symbol} size={30} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{trade.symbol.replace("/USDT", "")}<span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 12 }}>/USDT</span></div>
            <div style={{ color: "var(--muted)", fontSize: 11 }}>{friendlyStrategy(trade.strategy_name)} · {friendlyTradeRegime(trade.regime)}</div>
          </div>
        </a>
        <Badge color={sideColor}>{trade.side.toUpperCase()}</Badge>
        <Badge color="var(--amber)">OPEN</Badge>
      </div>

      {/* Range bar */}
      <PnlBar trade={trade} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)", marginBottom: 10 }}>
        <span>SL {price4.format(trade.stop_loss)}</span>
        <span style={{ color: "var(--accent)" }}>Entry {price4.format(trade.entry_price)}</span>
        <span>TP {price4.format(trade.take_profit)}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        {[
          { label: "Leverage", value: `${trade.leverage}×` },
          { label: "Qty", value: trade.qty ? price4.format(trade.qty) : "—" },
          { label: "Opened", value: new Date(trade.opened_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: "var(--surface2)", borderRadius: 8, padding: "8px 10px" }}>
            <div style={{ color: "var(--muted)", fontSize: 10, marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 13, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</div>
          </div>
        ))}
      </div>

      <div style={{ color: "var(--muted)", fontSize: 10.5, marginTop: 8 }}>
        ${money.format(riskedAmt)} at risk
      </div>

      {trade.entry_reasoning.length > 0 && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
          <div style={{ color: "var(--muted)", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 3 }}>
            Thesis
          </div>
          <div style={{ color: "var(--text)", fontSize: 11, lineHeight: 1.5 }}>
            {specificReasoning(trade.entry_reasoning)}
          </div>
        </div>
      )}
    </div>
  );
}

// Exit reasons that are obvious from the win/loss color + amount already
// shown — no need to spell them out. Anything else (trailing exits, manual
// fixes, forced closes) is genuinely useful context, so it's kept.
const OBVIOUS_EXIT_REASONS = new Set(["take_profit", "stop_loss"]);
const EXIT_REASON_LABEL: Record<string, string> = {
  trailing_take_profit: "Trailing stop locked in the win",
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
  const snapshot = trade.indicator_snapshot as Record<string, unknown> | undefined;
  const riskedAmt = typeof snapshot?.actual_risk_usdt === "number"
    ? snapshot.actual_risk_usdt
    : Math.abs(trade.entry_price - trade.stop_loss) * trade.qty;
  const footerNote = noteworthyExitReason(trade.exit_reason) ?? specificReasoning(trade.entry_reasoning);
  return (
    <Link
      href={`/journal?trade=${trade.id}`}
      style={{ color: "inherit", textDecoration: "none", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6, cursor: "pointer" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <CoinLogo symbol={trade.symbol} size={20} />
        <span style={{ fontWeight: 600, fontSize: 13, flex: 1, minWidth: 0 }}>{trade.symbol.replace("/USDT", "")}</span>
        <Badge color={sideColor}>{trade.side.toUpperCase()}</Badge>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ color: pnlColor(pnl), fontWeight: 700, fontSize: 15, fontVariantNumeric: "tabular-nums" }}>
            {pnl >= 0 ? "+" : ""}{money.format(pnl)} <span style={{ fontSize: 10, fontWeight: 400, color: "var(--muted)" }}>USDT</span>
          </span>
          {pnlPct !== undefined && (
            <span style={{ color: pnlColor(pnlPct), fontSize: 11, fontWeight: 600 }}>
              ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)
            </span>
          )}
        </div>
        <span style={{ color: "var(--muted)", fontSize: 10 }}>
          {trade.closed_at ? new Date(trade.closed_at).toLocaleDateString([], { month: "short", day: "numeric" }) : "—"}
        </span>
      </div>
      <div style={{ color: "var(--muted)", fontSize: 10.5 }}>
        ${money.format(riskedAmt)} at risk
      </div>
      <div style={{ color: "var(--muted)", fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {footerNote}
      </div>
    </Link>
  );
}


// ── card shell ───────────────────────────────────────────────────────────────
function Card({ title, right, children, noPad }: { title: string; right?: React.ReactNode; children: React.ReactNode; noPad?: boolean }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 20px", borderBottom: "1px solid var(--border)" }}>
        <span style={{ fontWeight: 600, fontSize: 12, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>{title}</span>
        {right}
      </div>
      <div style={noPad ? {} : { padding: "0 20px" }}>{children}</div>
    </div>
  );
}

// ── kill switch button ───────────────────────────────────────────────────────
function KillSwitchButton({ killActive, toggling, confirming, onHalt, onConfirm, onCancel, onResume, cancelRef }: {
  killActive?: boolean; toggling: boolean; confirming: boolean;
  onHalt: () => void; onConfirm: () => void; onCancel: () => void; onResume: () => void;
  cancelRef: React.RefObject<HTMLButtonElement | null>;
}) {
  if (confirming) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ color: "var(--muted)", fontSize: 12 }}>Confirm halt?</span>
      <button onClick={onConfirm} disabled={toggling} aria-label="Confirm halt"
        style={{ background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.5)", color: "var(--red)", borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
        Yes, halt
      </button>
      <button ref={cancelRef} onClick={onCancel} aria-label="Cancel"
        style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)", borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
        Cancel
      </button>
    </div>
  );

  if (killActive) return (
    <button onClick={onResume} disabled={toggling} aria-label="Resume trading"
      style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "var(--red)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 10 }}>▶</span> {toggling ? "Resuming…" : "Resume trading"}
    </button>
  );

  return (
    <button onClick={onHalt} disabled={toggling} aria-label="Halt new entries"
      style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--red)", display: "inline-block" }} />
      {toggling ? "Halting…" : "Halt entries"}
    </button>
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
  const [coinDigests, setCoinDigests] = useState<CoinDigest[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling,      setToggling]      = useState(false);
  const [confirmingHalt,setConfirmingHalt]= useState(false);
  const [error,         setError]         = useState<string | null>(null);
  const [toggleError,   setToggleError]   = useState<string | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  async function load() {
    try {
      const [s, st, t, details, live, digests] = await Promise.all([
        api.summary(),
        api.agentStatus(),
        api.trades(15),
        api.openPositionDetails(),
        api.livePositions().catch(() => []),
        api.coinDigests().catch(() => []),
      ]);
      setSummary(s); setStatus(st); setTrades(t); setPositionDetails(details); setCoinDigests(digests); setError(null);
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
    const d = new Date(status.checked_at);
    return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " +
           d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }, [status?.checked_at]);

  const openTrades   = trades.filter(t => !t.closed_at);
  const openCount    = positionDetails.length || openTrades.length;
  const closedTrades = trades.filter(t =>  t.closed_at);
  const killActive   = summary?.kill_switch_active;
  const regime       = status?.macro_regime || "normal";
  const regimeMeta   = REGIME_META[regime] || { label: regime, color: "var(--muted)" };
  const totalPnl     = closedTrades.reduce((sum, t) => sum + (t.pnl_usdt ?? 0), 0);

  return (
    <div style={{ minHeight: "100dvh", background: "var(--bg)", display: "flex" }}>
      <Sidebar />
      <div style={{ flex: 1, minWidth: 0 }}>

      {/* HALTED banner */}
      {killActive && (
        <div role="status" aria-live="polite"
          style={{ background: "rgba(239,68,68,0.08)", borderBottom: "1px solid rgba(239,68,68,0.25)", color: "var(--red)", padding: "9px 24px", fontSize: 12, fontWeight: 600, textAlign: "center", letterSpacing: "0.05em" }}>
          ▐▐ TRADING HALTED — all new entries blocked
        </div>
      )}

      <main style={{ maxWidth: 1560, margin: "0 auto", padding: "28px 28px 60px" }}>

        {/* Header row */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Dashboard</h1>
              {killActive && <Badge color="var(--red)">HALTED</Badge>}
            </div>
            <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>
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
          <div role="alert" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)", borderRadius: 10, padding: "10px 16px", fontSize: 12, marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <span>{error}</span>
            <button onClick={load} style={{ background: "none", border: "none", color: "var(--red)", textDecoration: "underline", cursor: "pointer", fontSize: 12, flexShrink: 0 }}>Retry</button>
          </div>
        )}
        {toggleError && (
          <div role="alert" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)", borderRadius: 10, padding: "10px 16px", fontSize: 12, marginBottom: 16 }}>
            {toggleError}
          </div>
        )}

        {/* Stat row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 18 }}>
          <StatCard label="Bankroll" value={summary ? `$${money.format(summary.bankroll_usdt)}` : "—"} sub="USDT balance" loading={loading} accent="var(--accent)" />
          <StatCard label="ROI" value={summary ? pct(summary.roi_pct) : "—"} color={summary ? pnlColor(summary.roi_pct) : undefined} sub="all-time" loading={loading} accent={summary ? pnlColor(summary.roi_pct) : undefined} />
          <StatCard label="Realized P&L" value={closedTrades.length ? `${totalPnl >= 0 ? "+" : ""}$${money.format(totalPnl)}` : "—"} color={pnlColor(totalPnl)} sub={`${closedTrades.length} closed trades`} loading={loading} accent={pnlColor(totalPnl)} />
          <StatCard label="Win Rate" value={summary ? `${summary.win_rate_pct.toFixed(1)}%` : "—"} sub={summary ? `${summary.total_trades} total` : undefined} loading={loading} accent={summary ? (summary.win_rate_pct >= 50 ? "var(--green)" : "var(--amber)") : undefined} />
          <StatCard label="Open" value={summary ? String(summary.open_positions) : "—"} color={summary && summary.open_positions > 0 ? "var(--amber)" : undefined} sub="positions" loading={loading} accent={summary && summary.open_positions > 0 ? "var(--amber)" : undefined} />
          <StatCard label="Macro" value={regimeMeta.label} color={regimeMeta.color} sub={`size ×${status ? (status as AgentStatus & { size_multiplier?: number }).size_multiplier?.toFixed(2) ?? "—" : "—"}`} loading={loading} accent={regimeMeta.color} />
        </div>

        {/* Open positions */}
        <div style={{ marginBottom: 18 }}>
          <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <h2 style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", margin: 0 }}>Open Positions</h2>
            {openCount > 0 && <Badge color="var(--amber)">{openCount}</Badge>}
          </div>
          {positionDetails.length > 0 ? (
            <div className="open-position-list" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 10 }}>
              {positionDetails.map(d => (
                <DetailedOpenPosition
                  key={d.trade.id}
                  detail={d}
                  payload={candlePayloads[d.trade.symbol]}
                  live={livePositions[d.trade.symbol]}
                />
              ))}
            </div>
          ) : openTrades.length > 0 ? (
            <div className="open-position-list" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 10 }}>
              {openTrades.map(t => <OpenPosition key={t.id} trade={t} />)}
            </div>
          ) : (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, minHeight: 90, padding: 16, color: "var(--muted)", fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center" }}>
              {loading ? "Loading positions..." : "No open position right now — the agent is scanning every active coin and will open one once a good setup shows up."}
            </div>
          )}
        </div>

        {/* Recent closed trades */}
        <Card title="Recent Closed Trades" right={<a href="/journal" style={{ color: "var(--accent)", fontSize: 11, textDecoration: "none" }}>View all →</a>} noPad>
          <div style={{ padding: "12px 20px 16px" }}>
            {loading ? (
              <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>Loading…</div>
            ) : closedTrades.length > 0 ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
                {closedTrades.map(t => <TradeRow key={t.id} trade={t} />)}
              </div>
            ) : (
              <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>No closed trades yet</div>
            )}
          </div>
        </Card>

        {/* Coin watch: daily price action + agent read + news sentiment per coin */}
        <div style={{ marginTop: 18 }}>
          <Card title="Coin Watch" right={<span style={{ color: "var(--muted)", fontSize: 11 }}>Refreshed daily, ~9 PM PH</span>} noPad>
            {coinDigests.length > 0 ? (
              <div style={{ padding: "12px 20px 16px", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
                {coinDigests.map(d => <CoinDigestCard key={d.symbol} digest={d} />)}
              </div>
            ) : (
              <div style={{ padding: "24px 20px", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
                {loading ? "Loading…" : "No digest yet today — the agent builds one for every coin once a day, around 9 PM PH. Check back after the next run."}
              </div>
            )}
          </Card>
        </div>

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
