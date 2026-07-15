"use client";

import { useEffect, useState } from "react";
import { CheckCircle, Circle } from "@phosphor-icons/react";
import { api, StrategyOverview } from "@/lib/api";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-[#1b303d] bg-[#071017] p-3">
      <h2 className="border-b border-[#1b303d] pb-3 text-[11px] font-semibold tracking-[.08em] text-[#a9b7c2]">{title}</h2>
      <div className="pt-3">{children}</div>
    </section>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return <><span className="text-[#83939f]">{label}</span><span>{value}</span></>;
}

export default function StrategyPage() {
  const [strategy, setStrategy] = useState<StrategyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => api.strategy().then((s) => active && setStrategy(s)).catch(() => active && setError("Could not load strategy config from the backend."));
    load();
    const timer = window.setInterval(load, 30000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  return (
    <div className="min-h-screen min-w-[1150px] bg-[#03080d] text-[#dce5ed]">
      <main className="px-4 py-3">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-[21px] font-semibold">Strategy</h1>
            <span className="text-[10px] text-[#82929e]">Live config, straight from the server</span>
          </div>
        </header>

        {error && <div className="mt-3 border border-[#765b20] bg-[#2a220f] px-3 py-2 text-[11px] text-[#eab83c]">{error}</div>}

        <section className="mt-3 grid grid-cols-4 border border-[#1b303d] bg-[#071017]">
          <div className="border-r border-[#1b303d] p-3">
            <span className="text-[9px] text-[#8999a5]">ACTIVE PROFILE</span>
            <strong className="mt-1 block text-[15px] text-[#43aaff]">{strategy?.profile.name ?? "—"}</strong>
          </div>
          <div className="border-r border-[#1b303d] p-3">
            <span className="text-[9px] text-[#8999a5]">EXCHANGE / ENV</span>
            <strong className="mt-1 block text-[14px]">{strategy?.execution.exchange ?? "—"} {strategy?.execution.testnet ? "(testnet)" : "(live)"}</strong>
          </div>
          <div className="border-r border-[#1b303d] p-3">
            <span className="text-[9px] text-[#8999a5]">TIMEFRAME</span>
            <strong className="mt-1 block text-[14px]">{strategy?.execution.timeframe ?? "—"}</strong>
          </div>
          <div className="p-3">
            <span className="text-[9px] text-[#8999a5]">EVALUATION CADENCE</span>
            <strong className="mt-1 block text-[12px]">{strategy?.execution.evaluation ?? "—"}</strong>
          </div>
        </section>

        <div className="mt-3 grid grid-cols-2 gap-3">
          <Card title="DECISION-ACTIVE MODULES">
            <ul className="text-[11px]">
              {(strategy?.profile.decision_active ?? []).map((m) => (
                <li key={m} className="flex items-center gap-2 border-b border-[#172a35] py-2 text-[#5db7ff]"><CheckCircle size={13} />{m}</li>
              ))}
            </ul>
          </Card>
          <Card title="OBSERVE-ONLY MODULES">
            <ul className="text-[11px]">
              {(strategy?.profile.observe_only ?? []).length ? (strategy?.profile.observe_only ?? []).map((m) => (
                <li key={m} className="flex items-center gap-2 border-b border-[#172a35] py-2 text-[#eab52e]"><Circle size={13} />{m} <span className="text-[#8797a2]">— data collected, not used in decisions</span></li>
              )) : <li className="py-2 text-[#8797a2]">None — every module is decision-active in this profile.</li>}
            </ul>
          </Card>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-3">
          <Card title="ENTRY RULES">
            <div className="grid grid-cols-1 gap-4 text-[10px]">
              <div>
                <h3 className="mb-3 text-[#54baff]">TREND-FOLLOWING</h3>
                {(strategy?.signals.trend_following ?? []).map((x) => <p key={x} className="mb-3 flex gap-2"><CheckCircle size={13} className="text-[#54baff]" />{x}</p>)}
              </div>
              <div>
                <h3 className="mb-3 text-[#e0b733]">MEAN-REVERSION</h3>
                {(strategy?.signals.mean_reversion ?? []).map((x) => <p key={x} className="mb-3 flex gap-2"><Circle size={13} className="text-[#e0b733]" />{x}</p>)}
              </div>
              <div>
                <h3 className="mb-3 text-[#ff6167]">HARD BLOCKS</h3>
                {(strategy?.signals.hard_blocks ?? []).map((x) => <p key={x} className="mb-3 flex gap-2">· {x}</p>)}
              </div>
            </div>
          </Card>
          <Card title="RISK & EXIT BEHAVIOR">
            <div className="grid grid-cols-[1fr_1fr] gap-y-3 text-[11px]">
              <KV label="Risk per Trade" value={strategy ? `${strategy.risk.max_risk_per_trade_pct}%` : "—"} />
              <KV label="Max Concurrent Positions" value={strategy?.risk.max_concurrent_positions ?? "—"} />
              <KV label="Portfolio Risk Cap" value={strategy ? `${strategy.risk.max_portfolio_risk_pct}%` : "—"} />
              <KV label="Same-Direction Risk Cap" value={strategy ? `${strategy.risk.max_same_direction_risk_pct}%` : "—"} />
              <KV label="Leverage" value={strategy ? `${strategy.risk.default_leverage}x (max ${strategy.risk.max_leverage}x)` : "—"} />
              <KV label="Daily Drawdown Cap" value={strategy ? `${strategy.risk.daily_drawdown_pct}%` : "—"} />
              <KV label="Stop Loss" value={strategy?.management.stop_loss ?? "—"} />
              <KV label="Take Profit" value={strategy?.management.take_profit ?? "—"} />
              <KV label="Trailing Stop" value={strategy?.management.regular_trailing ?? "—"} />
              <KV label="Trailing Take Profit" value={strategy?.management.trailing_take_profit ?? "—"} />
              <KV label="Max Hold" value={strategy?.management.max_hold ?? "—"} />
            </div>
          </Card>
          <Card title="COST & EDGE GATES">
            <div className="grid grid-cols-[1fr_1fr] gap-y-3 text-[11px]">
              <KV label="Taker Fee" value={strategy ? `${strategy.costs.taker_fee_pct}%` : "—"} />
              <KV label="Slippage Estimate" value={strategy ? `${strategy.costs.slippage_pct}%` : "—"} />
              <KV label="Min EV (live)" value={strategy ? `${strategy.costs.min_live_ev_r}R` : "—"} />
              <KV label="Min Edge After Cost" value={strategy ? `${strategy.costs.min_edge_after_cost_r}R` : "—"} />
              <KV label="Max Estimated Cost" value={strategy ? `${strategy.costs.max_estimated_cost_r}R` : "—"} />
              <KV label="Min Net EV After Cost" value={strategy ? `${strategy.costs.min_net_ev_after_cost_r}R` : "—"} />
              <KV label="Re-entry / Symbol / Day" value={strategy?.management.reentry.max_trades_per_symbol_per_day ?? "—"} />
              <KV label="Re-entry Min EV Multiplier" value={strategy?.management.reentry.min_ev_multiplier ?? "—"} />
              <KV label="News Sentiment" value={strategy?.context.news_enabled ? `enabled (${strategy.context.news_provider})` : "disabled"} />
            </div>
          </Card>
        </div>

        <div className="mt-3">
          <Card title="MARKET SCANNER">
            <div className="grid grid-cols-4 gap-y-3 text-[11px]">
              <KV label="Enabled" value={strategy?.scanner.enabled ? "Yes" : "No"} />
              <KV label="Roster Size (Top N)" value={strategy?.scanner.top_n ?? "—"} />
              <KV label="Refresh Interval" value={strategy ? `${strategy.scanner.refresh_minutes} min` : "—"} />
              <KV label="Min Quote Volume" value={strategy?.scanner.min_quote_volume ?? "—"} />
              <KV label="Max Spread" value={strategy ? `${strategy.scanner.max_spread_pct}%` : "—"} />
              <KV label="Fixed Majors" value={strategy?.scanner.fixed_majors?.join(", ") || "—"} />
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
