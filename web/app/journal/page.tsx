"use client";

import { useEffect, useMemo, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import { api, Trade } from "@/lib/api";

const money = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const price = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

function outcomeColor(trade: Trade) {
  if (trade.pnl_usdt == null) return "var(--amber)";
  return trade.pnl_usdt >= 0 ? "var(--green)" : "var(--red)";
}

function TradeRow({ trade }: { trade: Trade }) {
  const [open, setOpen] = useState(false);
  const color = outcomeColor(trade);
  const pnl = trade.pnl_usdt == null ? "open" : `${trade.pnl_usdt >= 0 ? "+" : ""}${money.format(trade.pnl_usdt)} USDT`;

  return (
    <div style={{ borderBottom: "1px solid var(--border)" }}>
      <button
        onClick={() => setOpen(!open)}
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
        }}
        className="journal-row"
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: 14 }}>{trade.symbol}</span>
            <span style={{ color: trade.side === "long" ? "var(--green)" : "var(--red)", background: `${trade.side === "long" ? "var(--green)" : "var(--red)"}18`, border: `1px solid ${trade.side === "long" ? "var(--green)" : "var(--red)"}30`, borderRadius: 6, padding: "2px 6px", fontSize: 11, fontWeight: 700 }}>
              {trade.side.toUpperCase()}
            </span>
          </div>
          <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 3 }}>{trade.strategy_name} / {trade.regime}</div>
        </div>
        <div style={{ color: "var(--muted)", fontSize: 12 }}>{trade.exit_reason || trade.entry_reasoning[0] || "-"}</div>
        <div style={{ color, fontWeight: 800, fontSize: 13, textAlign: "right" }}>{pnl}</div>
        <div style={{ color: "var(--muted)", fontSize: 12, textAlign: "right" }}>
          {new Date(trade.opened_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
        </div>
      </button>

      {open && (
        <div style={{ background: "var(--surface2)", borderTop: "1px solid var(--border)", padding: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(120px, 1fr))", gap: 10, marginBottom: 14 }} className="journal-detail-grid">
            {[
              ["Entry", price.format(trade.entry_price)],
              ["Exit", trade.exit_price == null ? "-" : price.format(trade.exit_price)],
              ["SL", price.format(trade.stop_loss)],
              ["TP", price.format(trade.take_profit)],
              ["Risked", `$${money.format(
                typeof (trade.indicator_snapshot as Record<string, unknown>)?.actual_risk_usdt === "number"
                  ? (trade.indicator_snapshot as Record<string, number>).actual_risk_usdt
                  : Math.abs(trade.entry_price - trade.stop_loss) * trade.qty
              )}`],
            ].map(([label, value]) => (
              <div key={label} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "9px 10px", background: "var(--surface)" }}>
                <div style={{ color: "var(--muted)", fontSize: 10, marginBottom: 3 }}>{label}</div>
                <div style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, fontSize: 13 }}>{value}</div>
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }} className="journal-notes-grid">
            <div>
              <div style={{ color: "var(--muted)", fontSize: 11, fontWeight: 700, marginBottom: 6 }}>Entry reasoning</div>
              <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text)", fontSize: 12, lineHeight: 1.6 }}>
                {trade.entry_reasoning.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
            <div>
              <div style={{ color: "var(--muted)", fontSize: 11, fontWeight: 700, marginBottom: 6 }}>Post-mortem</div>
              {trade.postmortem.length > 0 ? (
                <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text)", fontSize: 12, lineHeight: 1.6 }}>
                  {trade.postmortem.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              ) : (
                <div style={{ color: "var(--muted)", fontSize: 12 }}>No post-mortem yet.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function JournalContent() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.trades(100).then(setTrades).catch(() => setError("Could not load trades"));
  }, []);

  const stats = useMemo(() => {
    const closed = trades.filter(t => t.closed_at);
    const pnl = closed.reduce((sum, t) => sum + (t.pnl_usdt || 0), 0);
    const wins = closed.filter(t => (t.pnl_usdt || 0) > 0).length;
    return {
      closed: closed.length,
      pnl,
      winRate: closed.length ? (wins / closed.length) * 100 : 0,
    };
  }, [trades]);

  return (
    <div style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main style={{ flex: 1, minWidth: 0, maxWidth: 1560, margin: "0 auto", padding: "28px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Trade Journal</h1>
            <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>{trades.length} recorded trades</p>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}>
            {[
              ["Closed", String(stats.closed)],
              ["Win Rate", `${stats.winRate.toFixed(1)}%`],
              ["P&L", `${stats.pnl >= 0 ? "+" : ""}${money.format(stats.pnl)} USDT`],
            ].map(([label, value]) => (
              <div key={label} style={{ minWidth: 120, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px" }}>
                <div style={{ color: "var(--muted)", fontSize: 10, marginBottom: 3 }}>{label}</div>
                <div style={{ fontWeight: 800, fontSize: 13 }}>{value}</div>
              </div>
            ))}
          </div>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
          {trades.length > 0 ? (
            trades.map((trade) => <TradeRow key={trade.id} trade={trade} />)
          ) : (
            <div style={{ padding: 32, color: "var(--muted)", textAlign: "center", fontSize: 13 }}>No trades logged yet.</div>
          )}
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
