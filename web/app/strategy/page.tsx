"use client";

import { useEffect, useState } from "react";
import { CheckCircle, Circle, Eye, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import { Card, Badge } from "../components/ui";
import { api, StrategyOverview } from "@/lib/api";
import { money } from "@/lib/format";

function pctValue(value: number, digits = 2) {
  return `${value.toFixed(digits)}%`;
}

function yesNo(value: boolean) {
  return value ? "Yes" : "No";
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(140px, 0.75fr) 1fr", gap: 12, padding: "9px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>{label}</div>
      <div style={{ color: "var(--text)", fontSize: "var(--text-xs)", fontWeight: 600 }}>{value}</div>
    </div>
  );
}

function ChipList({ items, color = "var(--muted)" }: { items: string[]; color?: string }) {
  if (!items.length) return <span style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>None</span>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {items.map(item => (
        <span
          key={item}
          className="ui-badge"
          style={{
            color,
            background: "var(--surface2)",
            borderColor: "var(--border)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function RuleList({ items, icon = "check" }: { items: string[]; icon?: "check" | "block" }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      {items.map(item => (
        <div key={item} style={{ display: "flex", gap: 8, alignItems: "flex-start", color: "var(--text)", fontSize: "var(--text-xs)", lineHeight: 1.45 }}>
          {icon === "check"
            ? <CheckCircle size={15} weight="fill" color="var(--green)" style={{ marginTop: 1, flexShrink: 0 }} />
            : <WarningCircle size={15} weight="fill" color="var(--amber)" style={{ marginTop: 1, flexShrink: 0 }} />}
          <span>{item}</span>
        </div>
      ))}
    </div>
  );
}

function StrategyContent() {
  const [strategy, setStrategy] = useState<StrategyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.strategy()
      .then(data => { if (!cancelled) setStrategy(data); })
      .catch(() => { if (!cancelled) setError("Could not load strategy"); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 1120, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
          <div>
            <h1 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0 }}>Strategy</h1>
            <p style={{ color: "var(--muted)", fontSize: "var(--text-xs)", margin: "4px 0 0" }}>Current live rules from backend config.</p>
          </div>
          {strategy && (
            <Badge color={strategy.execution.testnet ? "var(--amber)" : "var(--red)"}>
              {strategy.execution.testnet ? "TESTNET" : "LIVE"}
            </Badge>
          )}
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: "var(--text-sm)", marginBottom: 12 }}>{error}</div>}

        {!strategy ? (
          <Card>
            <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>Loading strategy...</div>
          </Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
              <Card title="Profile">
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 12 }}>
                  <div style={{ fontSize: "var(--text-lg)", fontWeight: 750 }}>{strategy.profile.name}</div>
                  <Badge color={strategy.profile.name === "full_agentic" ? "var(--amber)" : "var(--accent)"}>
                    {strategy.profile.name === "full_agentic" ? "full stack" : "baseline"}
                  </Badge>
                </div>
                <Row label="Decides trades" value={<ChipList items={strategy.profile.decision_active} color="var(--green)" />} />
                <Row label="Observes only" value={<ChipList items={strategy.profile.observe_only} />} />
              </Card>

              <Card title="Execution">
                <Row label="Exchange" value={`${strategy.execution.exchange}${strategy.execution.testnet ? " testnet" : ""}`} />
                <Row label="Main candle" value={strategy.execution.timeframe} />
                <Row label="Evaluation" value={strategy.execution.evaluation} />
                <Row label="MTF stack" value={<ChipList items={strategy.execution.mtf_timeframes} color="var(--accent)" />} />
              </Card>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 0.9fr) minmax(360px, 1.1fr)", gap: 14 }}>
              <Card title="Market scanner">
                <Row label="Enabled" value={yesNo(strategy.scanner.enabled)} />
                <Row label="Shortlist" value={`${strategy.scanner.top_n} ranked coins; ${strategy.scanner.active_symbols} active slots`} />
                <Row label="Refresh" value={`${strategy.scanner.refresh_minutes} minutes`} />
                <Row label="Volume floor" value={money.format(strategy.scanner.min_quote_volume)} />
                <Row label="Spread ceiling" value={pctValue(strategy.scanner.max_spread_pct)} />
                <Row label="24h move ceiling" value={pctValue(strategy.scanner.max_abs_24h_change_pct, 1)} />
                <Row label="Market-cap filter" value={strategy.scanner.require_market_cap_rank ? `Top ${strategy.scanner.min_market_cap_rank}` : "Off"} />
                <Row label="Mainnet liquidity" value={yesNo(strategy.scanner.use_mainnet_liquidity)} />
                <Row label="Fixed majors" value={<ChipList items={strategy.scanner.fixed_majors} color="var(--accent)" />} />
                <Row label="Excluded" value={<ChipList items={strategy.scanner.excluded_symbols} />} />
              </Card>

              <Card title="Signal logic">
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
                  <div>
                    <div style={{ display: "flex", gap: 7, alignItems: "center", fontSize: "var(--text-sm)", fontWeight: 700, marginBottom: 10 }}>
                      <Circle size={8} weight="fill" color="var(--green)" />
                      Trend-following
                    </div>
                    <RuleList items={strategy.signals.trend_following} />
                  </div>
                  <div>
                    <div style={{ display: "flex", gap: 7, alignItems: "center", fontSize: "var(--text-sm)", fontWeight: 700, marginBottom: 10 }}>
                      <Circle size={8} weight="fill" color="var(--accent)" />
                      Mean-reversion
                    </div>
                    <RuleList items={strategy.signals.mean_reversion} />
                  </div>
                </div>
                <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", gap: 7, alignItems: "center", fontSize: "var(--text-sm)", fontWeight: 700, marginBottom: 10 }}>
                    <ShieldCheck size={16} weight="fill" color="var(--amber)" />
                    Hard blocks
                  </div>
                  <RuleList items={strategy.signals.hard_blocks} icon="block" />
                </div>
              </Card>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 14 }}>
              <Card title="Risk">
                <Row label="Bankroll" value={`${money.format(strategy.risk.bankroll_usdt)} (${strategy.risk.bankroll_mode})`} />
                <Row label="Risk ceiling" value={pctValue(strategy.risk.max_risk_per_trade_pct, 2)} />
                <Row label="Slots" value={`${strategy.risk.max_concurrent_positions} max${strategy.risk.split_risk_across_slots ? ", split risk across slots" : ""}`} />
                <Row label="Portfolio cap" value={pctValue(strategy.risk.max_portfolio_risk_pct, 2)} />
                <Row label="Same-side cap" value={pctValue(strategy.risk.max_same_direction_risk_pct, 2)} />
                <Row label="Leverage" value={`${strategy.risk.default_leverage}x default; ${strategy.risk.max_leverage}x max`} />
                <Row label="Confidence sizing" value={strategy.risk.confidence_risk_scaling ? `Full size at ${strategy.risk.confidence_full_risk_at.toFixed(2)} confidence` : "Off"} />
                <Row label="Risk tiers" value={`base ${pctValue(strategy.risk.risk_base_pct, 2)} / recovery ${pctValue(strategy.risk.risk_recovery_pct, 2)} / drawdown ${pctValue(strategy.risk.risk_drawdown_pct, 2)} / proven ${pctValue(strategy.risk.risk_proven_pct, 2)}`} />
                <Row label="Daily kill-switch" value={pctValue(strategy.risk.daily_drawdown_pct, 2)} />
              </Card>

              <Card title="Cost gates">
                <Row label="Fee + slippage" value={`${pctValue(strategy.costs.taker_fee_pct, 2)} taker + ${pctValue(strategy.costs.slippage_pct, 2)} slippage`} />
                <Row label="Minimum live EV" value={`${strategy.costs.min_live_ev_r.toFixed(2)}R`} />
                <Row label="Edge after cost" value={`${strategy.costs.min_edge_after_cost_r.toFixed(2)}R`} />
                <Row label="Max estimated cost" value={`${strategy.costs.max_estimated_cost_r.toFixed(2)}R`} />
                <Row label="Net EV floor" value={`${strategy.costs.min_net_ev_after_cost_r.toFixed(2)}R`} />
                <Row label="Reward/cost floor" value={`${strategy.costs.min_expected_reward_cost_multiple.toFixed(0)}x`} />
                <Row label="Stop/cost floor" value={`${strategy.costs.min_stop_cost_multiple.toFixed(0)}x`} />
              </Card>

              <Card title="Management">
                <Row label="SL" value={strategy.management.stop_loss} />
                <Row label="TP" value={strategy.management.take_profit} />
                <Row label="Trailing stop" value={strategy.management.regular_trailing} />
                <Row label="TP runner" value={strategy.management.trailing_take_profit} />
                <Row label="Max hold" value={strategy.management.max_hold} />
                <Row label="Re-entry" value={`${strategy.management.reentry.max_trades_per_symbol_per_day}/symbol/day; setup needs ${strategy.management.reentry.min_ev_multiplier.toFixed(1)}x EV improvement`} />
              </Card>
            </div>

            <Card title="Context">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Eye size={16} color={strategy.context.news_enabled ? "var(--green)" : "var(--muted)"} />
                  <div>
                    <div style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>News context</div>
                    <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 2 }}>
                      {strategy.context.news_enabled ? `${strategy.context.news_provider}; digest around ${strategy.context.coin_digest_hour_ph}:00 PH` : "Off"}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Eye size={16} color={strategy.context.telegram_close_lessons ? "var(--amber)" : "var(--muted)"} />
                  <div>
                    <div style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>Telegram close lessons</div>
                    <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 2 }}>
                      {strategy.context.telegram_close_lessons ? "Included in close notifications" : "Silent / observe-only"}
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}

export default function StrategyPage() {
  return (
    <AuthGate>
      <StrategyContent />
    </AuthGate>
  );
}
