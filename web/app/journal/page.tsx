"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { WarningCircle } from "@phosphor-icons/react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import { api, Summary, Trade, TradeNarrative } from "@/lib/api";
import { Badge, StatCard } from "../components/ui";

const money = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const price = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

function outcomeColor(trade: Trade) {
  if (trade.pnl_usdt == null) return "var(--amber)";
  return trade.pnl_usdt >= 0 ? "var(--green)" : "var(--red)";
}

function TradeRow({ trade, isOpen, onToggle, rowRef, highlighted }: {
  trade: Trade; isOpen: boolean; onToggle: () => void; rowRef: (el: HTMLDivElement | null) => void; highlighted: boolean;
}) {
  const color = outcomeColor(trade);
  const pnl = trade.pnl_usdt == null ? "open" : `${trade.pnl_usdt >= 0 ? "+" : ""}${money.format(trade.pnl_usdt)} USDT`;
  const [narrative, setNarrative] = useState<TradeNarrative | null>(null);
  const [narrativeError, setNarrativeError] = useState(false);

  useEffect(() => {
    if (!isOpen || narrative || narrativeError) return;
    api.tradeNarrative(trade.id).then(setNarrative).catch(() => setNarrativeError(true));
  }, [isOpen, narrative, narrativeError, trade.id]);

  return (
    <div ref={rowRef} style={{ borderBottom: "1px solid var(--border)", background: highlighted ? "var(--surface2)" : "transparent", transition: "background var(--dur-base) var(--ease-out-quart)" }}>
      <button
        onClick={onToggle}
        style={{
          width: "100%",
          background: "transparent",
          border: 0,
          color: "var(--text)",
          cursor: "pointer",
          display: "grid",
          gridTemplateColumns: "minmax(180px, 1.2fr) minmax(160px, 1fr) 120px 180px",
          gap: 16,
          alignItems: "center",
          padding: "13px 16px",
          textAlign: "left",
          transition: "background var(--dur-base) var(--ease-out-quart)",
        }}
        className="journal-row"
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: "var(--text-base)" }}>{trade.symbol}</span>
            <Badge color={trade.side === "long" ? "var(--green)" : "var(--red)"}>{trade.side.toUpperCase()}</Badge>
          </div>
          <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)", marginTop: 3 }}>{trade.strategy_name} / {trade.regime}</div>
        </div>
        <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>{trade.exit_reason || trade.entry_reasoning[0] || "-"}</div>
        <div style={{ color, fontWeight: 800, fontSize: "var(--text-sm)", textAlign: "right" }}>{pnl}</div>
        <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)", textAlign: "right" }}>
          {new Date(trade.opened_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
        </div>
      </button>

      {isOpen && (
        <div style={{ background: "var(--surface2)", borderTop: "1px solid var(--border)", padding: 16 }} className="rise-in">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(120px, 1fr))", gap: 10, marginBottom: 14 }} className="journal-detail-grid">
            {[
              ["Entry", price.format(trade.entry_price)],
              ["Exit", trade.exit_price == null ? "-" : price.format(trade.exit_price)],
              ["Stop Loss", price.format(trade.stop_loss)],
              ["Take Profit", price.format(trade.take_profit)],
              ["At risk", `$${money.format(
                typeof (trade.indicator_snapshot as Record<string, unknown>)?.actual_risk_usdt === "number"
                  ? (trade.indicator_snapshot as Record<string, number>).actual_risk_usdt
                  : Math.abs(trade.entry_price - trade.stop_loss) * trade.qty
              )}`],
            ].map(([label, value]) => (
              <div key={label} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "9px 10px", background: "var(--surface)" }}>
                <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginBottom: 3 }}>{label}</div>
                <div style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, fontSize: "var(--text-sm)" }}>{value}</div>
              </div>
            ))}
          </div>

          {!narrative ? (
            <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>{narrativeError ? "Could not load reasoning." : "Loading reasoning…"}</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: "var(--text-2xs)", color: "var(--muted)" }}>
                {narrative.confidence !== null && <span>Conf {narrative.confidence.toFixed(2)}</span>}
                {narrative.ev_r !== null && <span>EV {narrative.ev_r >= 0 ? "+" : ""}{narrative.ev_r.toFixed(2)}R</span>}
                {narrative.risk_pct !== null && <span>Risk {narrative.risk_pct.toFixed(2)}%</span>}
                <span>R:R {narrative.rr.toFixed(1)}</span>
              </div>

              <div>
                <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", fontWeight: 700, marginBottom: 4 }}>Thesis</div>
                <div style={{ color: "var(--text)", fontSize: "var(--text-xs)", lineHeight: 1.6 }}>{narrative.thesis_lines.join(" ")}</div>
              </div>

              {narrative.why_accepted_lines.length > 0 && (
                <div>
                  <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", fontWeight: 700, marginBottom: 4 }}>Why accepted</div>
                  <div style={{ color: "var(--text)", fontSize: "var(--text-xs)", lineHeight: 1.6 }}>{narrative.why_accepted_lines.join(" ")}</div>
                </div>
              )}

              {narrative.weakness_line && (
                <div style={{ color: "var(--amber)", fontSize: "var(--text-xs)", lineHeight: 1.5, display: "flex", gap: 4 }}>
                  <WarningCircle size={13} style={{ flexShrink: 0, marginTop: 2 }} /> Weakness: {narrative.weakness_line}
                </div>
              )}

              <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)", lineHeight: 1.5 }}>Invalidation: {narrative.invalidation_line}</div>

              {narrative.past_context_line && (
                <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)", lineHeight: 1.5 }}>Past context: {narrative.past_context_line}</div>
              )}

              {narrative.outcome && (
                <>
                  <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
                    <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", fontWeight: 700, marginBottom: 4 }}>
                      {narrative.outcome === "loss" ? "Why it failed" : "Result"}
                    </div>
                    <div style={{ color: "var(--text)", fontSize: "var(--text-xs)", lineHeight: 1.6 }}>{narrative.failure_line}</div>
                  </div>
                  {narrative.lesson_line && (
                    <div>
                      <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", fontWeight: 700, marginBottom: 4 }}>Lesson</div>
                      <div style={{ color: "var(--text)", fontSize: "var(--text-xs)", lineHeight: 1.6 }}>{narrative.lesson_line}</div>
                    </div>
                  )}
                  <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>
                    Exit reason: {narrative.exit_reason || "—"} · R: {narrative.r_multiple !== null ? `${narrative.r_multiple >= 0 ? "+" : ""}${narrative.r_multiple.toFixed(1)}R` : "—"} · Held: {narrative.held_duration || "—"}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function JournalContent() {
  const searchParams = useSearchParams();
  const highlightId = searchParams.get("trade") ? Number(searchParams.get("trade")) : null;

  const [trades, setTrades] = useState<Trade[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rowRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    api.trades(100).then(setTrades).catch(() => setError("Could not load trades"));
    api.summary().then(setSummary).catch(() => {});
  }, []);

  useEffect(() => {
    if (highlightId === null || trades.length === 0) return;
    setOpenId(highlightId);
    const el = rowRefs.current[highlightId];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightId, trades.length]);

  const stats = useMemo(() => {
    // Prefer the backend's all-time totals (summary) — trades is capped at
    // the last 100 fetched, so summing it directly would silently disagree
    // with the true total once there are more than 100 closed trades.
    if (summary) {
      return { closed: summary.total_trades, pnl: summary.total_pnl_usdt, winRate: summary.win_rate_pct };
    }
    const closed = trades.filter(t => t.closed_at);
    const pnl = closed.reduce((sum, t) => sum + (t.pnl_usdt || 0), 0);
    const wins = closed.filter(t => (t.pnl_usdt || 0) > 0).length;
    return {
      closed: closed.length,
      pnl,
      winRate: closed.length ? (wins / closed.length) * 100 : 0,
    };
  }, [trades, summary]);

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 1560, margin: "0 auto" }}>
        <div className="header-row" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 18, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0 }}>Trade Journal</h1>
            <p style={{ color: "var(--muted)", fontSize: "var(--text-xs)", margin: "4px 0 0" }}>{trades.length} recorded trades</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(110px, 1fr))", gap: 10 }}>
            <StatCard label="Closed" value={String(stats.closed)} />
            <StatCard label="Win Rate" value={`${stats.winRate.toFixed(1)}%`} />
            <StatCard label="P&L" value={`${stats.pnl >= 0 ? "+" : ""}${money.format(stats.pnl)}`} color={stats.pnl >= 0 ? "var(--green)" : "var(--red)"} accent={stats.pnl >= 0 ? "var(--green)" : "var(--red)"} />
          </div>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: "var(--text-sm)", marginBottom: 12 }}>{error}</div>}

        <div className="ui-card">
          {trades.length > 0 ? (
            trades.map((trade) => (
              <TradeRow
                key={trade.id}
                trade={trade}
                isOpen={openId === trade.id}
                onToggle={() => setOpenId(openId === trade.id ? null : trade.id)}
                rowRef={(el) => { rowRefs.current[trade.id] = el; }}
                highlighted={highlightId === trade.id}
              />
            ))
          ) : (
            <div style={{ padding: 32, color: "var(--muted)", textAlign: "center", fontSize: "var(--text-sm)" }}>No trades logged yet.</div>
          )}
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <Suspense fallback={<div style={{ padding: 32, color: "var(--muted)" }}>Loading…</div>}>
        <JournalContent />
      </Suspense>
    </AuthGate>
  );
}
