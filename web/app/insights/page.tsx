"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowClockwise, ShieldWarning } from "@phosphor-icons/react";
import { api, InsightsPayload } from "@/lib/api";

function money(value: unknown) {
  if (typeof value !== "number") return "—";
  const sign = value >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pct(value: unknown) {
  if (typeof value !== "number") return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="border border-[#1a303b] bg-[#071118]">
      <div className="border-b border-[#1a303b] px-4 py-3">
        <div className="text-[13px] font-semibold">{title}</div>
        {subtitle && <div className="mt-1 text-[10px] text-[#8595a1]">{subtitle}</div>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export default function InsightsPage() {
  const [data, setData] = useState<InsightsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      api.insights()
        .then((next) => active && setData(next))
        .catch(() => active && setError("Could not load insights from the backend."));
    };
    load();
    const timer = window.setInterval(load, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const recommendationStyle = useMemo(() => (index: number) => index === 0 ? "border-[#583a6e] bg-[#1b1225] text-[#d7b0ff]" : "border-[#27384b] bg-[#09141b] text-[#dbe6ef]", []);
  const exitBreakdown = (data?.trading.exit_breakdown as Record<string, number> | undefined) ?? {};
  const byStrategy = (data?.trading.by_strategy as Record<string, { pnl: number; count: number }> | undefined) ?? {};

  if (!data && !error) {
    return <div className="grid min-h-screen place-items-center bg-[#04090e] text-[13px] text-[#8ea0ad]">Loading insights…</div>;
  }

  return (
    <div className="min-h-screen bg-[#04090e] text-[#dce5ed]">
      <main className="px-6 py-6">
        <header className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-[22px] font-semibold">Insights</h1>
            <p className="mt-1 text-[12px] text-[#8495a3]">A backend-generated summary of validation, scan quality, exits, and decision pressure.</p>
          </div>
          <button onClick={() => api.insights().then(setData).catch(() => setError("Could not refresh insights."))} className="inline-flex items-center gap-2 border border-[#304250] bg-[#09131a] px-3 py-2 text-[11px] text-[#dbe5ed]">
            <ArrowClockwise size={15} /> Refresh
          </button>
        </header>

        {error && <div className="mt-4 border border-[#765b20] bg-[#2a220f] px-3 py-2 text-[11px] text-[#eab83c]">{error}</div>}

        <section className="mt-4 grid grid-cols-5 border border-[#1c303b] bg-[#071118]">
          {(data?.signals ?? []).map((item, index) => (
            <div key={item.title} className={`border-r border-[#1c303b] px-4 py-3 last:border-r-0 ${index === 0 ? "border-t-2 border-t-[#3186ff]" : ""}`}>
              <div className="text-[10px] text-[#98a9b5]">{item.title}</div>
              <div className="mt-2 text-[18px] font-semibold">{item.value}</div>
              <div className="mt-1 text-[10px] text-[#83939f]">{item.note}</div>
            </div>
          ))}
        </section>

        <div className="mt-4 grid grid-cols-2 gap-4">
          <Card title="Risk and validation" subtitle="What the bot is currently allowed to do">
            <div className="grid grid-cols-2 gap-3 text-[11px]">
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Risk tier</div>
                <div className="mt-2 text-[16px] font-semibold">{String(data?.risk.tier ?? "—")}</div>
                <div className="mt-1 text-[#82939f]">Risk {pct(data?.risk.risk_pct)}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Drawdown</div>
                <div className="mt-2 text-[16px] font-semibold">{pct(data?.risk.drawdown_pct)}</div>
                <div className="mt-1 text-[#82939f]">{String(data?.risk.reason ?? "—")}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Validation</div>
                <div className="mt-2 text-[16px] font-semibold">{data?.validation.ready ? "READY" : "NOT READY"}</div>
                <div className="mt-1 text-[#82939f]">{String(data?.validation.days_elapsed ?? "—")}d elapsed / {String(data?.validation.days_remaining ?? "—")}d remaining</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Cost-aware edge</div>
                <div className="mt-2 text-[16px] font-semibold">{pct(data?.validation.expectancy_after_cost_r)}</div>
                <div className="mt-1 text-[#82939f]">PF {typeof data?.validation.profit_factor === "number" ? data.validation.profit_factor.toFixed(2) : "—"}</div>
              </div>
            </div>
            {Array.isArray(data?.validation.failed) && data?.validation.failed.length > 0 && (
              <div className="mt-4 border border-[#765b20] bg-[#2a220f] p-3 text-[11px] text-[#eab83c]">
                <div className="mb-2 flex items-center gap-2 font-semibold"><ShieldWarning size={14} />Blocking checks</div>
                <ul className="space-y-1">
                  {data.validation.failed.map((item) => <li key={item}>• {item}</li>)}
                </ul>
              </div>
            )}
          </Card>

          <Card title="Scanning and gating" subtitle="How much of the market made it through">
            <div className="grid grid-cols-2 gap-3 text-[11px]">
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Shortlisted</div>
                <div className="mt-2 text-[16px] font-semibold text-[#45dd84]">{data?.scan.scan.selected?.length ?? data?.scan.active.length ?? 0}</div>
                <div className="mt-1 text-[#82939f]">Eligible: {data?.scan.scan.eligible ?? "—"}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Scan status</div>
                <div className="mt-2 text-[16px] font-semibold">{data?.scan.scan.status ?? "—"}</div>
                <div className="mt-1 text-[#82939f]">Last scan: {data?.scan.scan.last_scan_at ? new Date(data.scan.scan.last_scan_at).toLocaleString() : "—"}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">24h gate pressure</div>
                <div className="mt-2 text-[16px] font-semibold">{String(exitBreakdown.trailing_stop ?? 0)}</div>
                <div className="mt-1 text-[#82939f]">Use Live Log for gate-level detail</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Open risk</div>
                <div className="mt-2 text-[16px] font-semibold">{money(data?.trading.open_risk_usdt)}</div>
                <div className="mt-1 text-[#82939f]">Current capital at stake</div>
              </div>
            </div>
            <div className="mt-4 text-[11px] text-[#92a1ae]">
              Gate rejects: 24h {data?.recent_activity?.length ?? 0} logged items · 7d pressure is summarized on the backend.
            </div>
          </Card>
        </div>

        <div className="mt-4 grid grid-cols-[1.15fr_.95fr] gap-4">
          <Card title="Execution quality" subtitle="What the exits are telling us">
            <div className="grid grid-cols-3 gap-3 text-[11px]">
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Trailing stops</div>
                <div className="mt-2 text-[16px] font-semibold">{String(exitBreakdown.trailing_stop ?? 0)}</div>
                <div className="mt-1 text-[#82939f]">vs TPs {String(exitBreakdown.take_profit ?? 0)}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Runner closes</div>
                <div className="mt-2 text-[16px] font-semibold">{String(data?.trading.runner_count ?? 0)}</div>
                <div className="mt-1 text-[#82939f]">Runner P&L {money(data?.trading.runner_pnl_usdt)}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Small wins</div>
                <div className="mt-2 text-[16px] font-semibold">{String(data?.trading.tiny_win_count ?? 0)}</div>
                <div className="mt-1 text-[#82939f]">Cost floor pressure {pct(data?.trading.avg_estimated_cost_r)}</div>
              </div>
            </div>
            <div className="mt-4 grid gap-2 text-[11px]">
              <div className="flex items-center justify-between rounded border border-[#213443] bg-[#09131a] px-3 py-2">
                <span>Top strategy</span>
                <span className="font-mono text-[#45dd84]">{Object.entries(byStrategy).sort((a, b) => b[1].pnl - a[1].pnl)[0]?.[0] ?? "—"}</span>
              </div>
              <div className="flex items-center justify-between rounded border border-[#213443] bg-[#09131a] px-3 py-2">
                <span>Re-entry count</span>
                <span className="font-mono">{String(data?.trading.reentry_count ?? 0)}</span>
              </div>
              <div className="flex items-center justify-between rounded border border-[#213443] bg-[#09131a] px-3 py-2">
                <span>High-cost trades</span>
                <span className="font-mono">{String(data?.trading.high_cost_trade_count ?? 0)}</span>
              </div>
            </div>
          </Card>

          <Card title="Recommendations" subtitle="Backend-generated talking points">
            <div className="space-y-2 text-[11px] leading-[1.6]">
              {(data?.recommendations ?? []).length ? data!.recommendations.map((item, index) => (
                <div key={index} className={`rounded border px-3 py-2 ${recommendationStyle(index)}`}>
                  {item}
                </div>
              )) : <div className="text-[#8495a3]">No recommendation text yet.</div>}
            </div>
          </Card>
        </div>

        <div className="mt-4 grid grid-cols-[1fr_1fr] gap-4">
          <Card title="Recent activity" subtitle="Latest cycle notes and adaptive events">
            <div className="space-y-2 text-[11px]">
              {(data?.recent_activity ?? []).slice(0, 10).map((entry) => (
                <div key={entry.id} className="rounded border border-[#213443] bg-[#09131a] px-3 py-2">
                  <div className="flex items-center justify-between text-[#82939f]">
                    <span>{entry.symbol ?? "—"} · {String(entry.level ?? "info").toUpperCase()}</span>
                    <span className="font-mono">{new Date(entry.created_at).toLocaleTimeString([], { hour12: false })}</span>
                  </div>
                  <div className="mt-1 text-[#dbe6ef]">{entry.message}</div>
                </div>
              ))}
            </div>
          </Card>
          <Card title="What the backend already knows" subtitle="A quick sanity strip so the UI stays grounded">
            <div className="grid grid-cols-2 gap-3 text-[11px]">
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Total P&L</div>
                <div className="mt-2 text-[16px] font-semibold">{money(data?.summary.total_pnl_usdt)}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Win rate</div>
                <div className="mt-2 text-[16px] font-semibold">{pct(data?.summary.win_rate_pct)}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Closed trades</div>
                <div className="mt-2 text-[16px] font-semibold">{String(data?.summary.closed_trades ?? "—")}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Open positions</div>
                <div className="mt-2 text-[16px] font-semibold">{String(data?.summary.open_positions ?? "—")}</div>
              </div>
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
