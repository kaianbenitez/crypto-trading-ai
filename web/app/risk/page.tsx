"use client";

import { useEffect, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import { api, RiskStatus, Validation } from "@/lib/api";
import { money, pct, pnlColor } from "@/lib/format";

const READINESS_LABEL: Record<string, string> = {
  sample_size: "Enough closed trades to trust the numbers",
  expectancy: "Average result per trade is positive enough",
  profit_factor: "Wins outweigh losses by a healthy margin",
  drawdown: "Worst losing streak stayed within bounds",
  symbol_diversity: "Results aren't riding on one coin alone",
  reentry_not_bleeding: "Re-entries aren't quietly losing money",
};

const TIER_LABEL: Record<string, string> = {
  fixed: "Fixed — a flat risk % every trade, no adjustment",
  normal: "Normal — default sizing while the strategy proves itself",
  proven: "Proven — 30-day validation passed, sizing increased",
  recovery: "Recovery — sizing reduced after a losing streak",
  drawdown: "Drawdown guard — sizing cut after a larger loss",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontWeight: 600, fontSize: 12, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)" }}>{title}</div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px" }}>
      <div style={{ color: "var(--muted)", fontSize: 10, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: color ?? "var(--text)", fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

function RiskContent() {
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.riskStatus(), api.validation()])
      .then(([r, v]) => { setRisk(r); setValidation(v); })
      .catch(() => setError("Could not load risk data"));
  }, []);

  const metrics = validation?.metrics;
  const readiness = validation?.readiness;

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 1200, margin: "0 auto" }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Risk</h1>
          <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>
            How much the agent is risking per trade right now, and whether its 30-day track record has earned bigger size.
          </p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

        {!risk ? (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Card title="Current risk setting">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10, marginBottom: 12 }}>
                <Stat label="Bankroll used for sizing" value={`$${money.format(risk.effective_bankroll_usdt)}`} />
                <Stat label="Risk per trade" value={`${risk.risk_pct.toFixed(2)}%`} />
                <Stat label="Recent drawdown" value={`${risk.drawdown_pct.toFixed(2)}%`} color={risk.drawdown_pct > 5 ? "var(--red)" : undefined} />
                <Stat label="Mode" value={risk.mode === "equity" ? "Tracks live exchange balance" : "Fixed configured amount"} />
              </div>
              <div style={{ color: "var(--muted)", fontSize: 12, lineHeight: 1.5 }}>
                <b style={{ color: "var(--text)" }}>{TIER_LABEL[risk.tier] ?? risk.tier}</b>
                <div style={{ marginTop: 4 }}>Why: {risk.reason}</div>
              </div>
            </Card>

            {metrics && readiness && (
              <Card title="30-day validation">
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10, marginBottom: 14 }}>
                  <Stat label="Closed trades" value={String(metrics.closed_count)} />
                  <Stat label="Win rate" value={`${metrics.win_rate_pct.toFixed(1)}%`} />
                  <Stat label="P&L" value={`${metrics.total_pnl_usdt >= 0 ? "+" : ""}$${money.format(metrics.total_pnl_usdt)}`} color={pnlColor(metrics.total_pnl_usdt)} />
                  <Stat label="ROI" value={pct(metrics.roi_pct)} color={pnlColor(metrics.roi_pct)} />
                  <Stat label="Avg result/trade" value={`${metrics.expectancy_r >= 0 ? "+" : ""}${metrics.expectancy_r.toFixed(2)}R`} color={pnlColor(metrics.expectancy_r)} />
                  <Stat label="Win $ vs loss $" value={`${metrics.profit_factor.toFixed(2)}x`} />
                  <Stat label="Worst drawdown" value={`${metrics.max_drawdown_pct.toFixed(2)}%`} />
                  <Stat label="Coins traded" value={String(metrics.distinct_symbols)} />
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: readiness.ready ? "var(--green)" : "var(--amber)" }}>
                    {readiness.ready ? "✅ Ready for bigger size" : "⏳ Not yet ready for bigger size"}
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {Object.entries(readiness.checks).map(([key, passed]) => (
                    <div key={key} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                      <span style={{ color: passed ? "var(--green)" : "var(--muted)" }}>{passed ? "✓" : "○"}</span>
                      <span style={{ color: passed ? "var(--text)" : "var(--muted)" }}>{READINESS_LABEL[key] ?? key}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {metrics && metrics.closed_count > 0 && (
              <Card title="Fees & cost drag">
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginBottom: 14 }}>
                  <Stat label="Avg estimated cost" value={`${metrics.avg_estimated_cost_r.toFixed(2)}R`} />
                  <Stat label="High-cost trades" value={String(metrics.high_cost_trade_count)} color={metrics.high_cost_trade_count > 0 ? "var(--amber)" : undefined} />
                  <Stat label="Avg net R after cost" value={`${metrics.avg_net_r_after_estimated_cost >= 0 ? "+" : ""}${metrics.avg_net_r_after_estimated_cost.toFixed(2)}R`} color={pnlColor(metrics.avg_net_r_after_estimated_cost)} />
                  <Stat label="Tiny wins (< +0.5R)" value={String(metrics.tiny_win_count)} color={metrics.tiny_win_count > metrics.closed_count * 0.3 ? "var(--amber)" : undefined} />
                </div>
                <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 10 }}>
                  &quot;Avg net R after cost&quot; is the realized result per trade minus the estimated round-trip fee/slippage —
                  if this is much lower than the raw expectancy above, fees are eating a meaningful share of the edge.
                </div>
                {Object.keys(metrics.exit_reason_breakdown).length > 0 && (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {Object.entries(metrics.exit_reason_breakdown).map(([reason, count]) => (
                      <div key={reason} style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", fontSize: 11 }}>
                        <span style={{ color: "var(--muted)" }}>{reason.replace(/_/g, " ")}: </span>
                        <span style={{ fontWeight: 700 }}>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            )}

            {metrics && Object.keys(metrics.by_symbol).length > 0 && (
              <Card title="By coin (last 30 days)">
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
                  {Object.entries(metrics.by_symbol).map(([sym, row]) => (
                    <div key={sym} style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px" }}>
                      <div style={{ fontWeight: 700, fontSize: 12 }}>{sym.replace("/USDT", "")}</div>
                      <div style={{ color: pnlColor(row.pnl), fontSize: 13, fontWeight: 700, marginTop: 2 }}>
                        {row.pnl >= 0 ? "+" : ""}${money.format(row.pnl)}
                      </div>
                      <div style={{ color: "var(--muted)", fontSize: 11 }}>{row.win_rate_pct.toFixed(0)}% WR, {row.avg_r >= 0 ? "+" : ""}{row.avg_r.toFixed(2)}R avg</div>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <RiskContent />
    </AuthGate>
  );
}
