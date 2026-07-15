"use client";

import { useEffect, useState } from "react";
import { api, AgentStatus, Summary } from "@/lib/api";
import {
  BookOpen,
  Broadcast,
  ChartLineUp,
  Eye,
  Gauge,
  GearSix,
  ShieldWarning,
} from "@phosphor-icons/react";

type NavItem = { label: string; icon: typeof Gauge };

const navItems: NavItem[] = [
  { label: "Dashboard", icon: Gauge },
  { label: "Live Log", icon: Broadcast },
  { label: "Journal", icon: BookOpen },
  { label: "Coin Watch", icon: Eye },
  { label: "Risk", icon: ShieldWarning },
  { label: "Strategy", icon: ChartLineUp },
  { label: "Settings", icon: GearSix },
];

const metrics = [
  ["EQUITY", "$102,846.21", "100.00%", "neutral"],
  ["DAY P&L", "+$2,341.76", "+2.34%", "profit"],
  ["UNREALIZED P&L", "+$1,128.35", "+1.10%", "profit"],
  ["REALIZED P&L (7D)", "+$4,786.21", "+4.87%", "profit"],
  ["TOTAL P&L (7D)", "+$5,914.56", "+6.04%", "profit"],
  ["BUYING POWER", "$72,341.88", "70.3%", "neutral"],
  ["MARGIN USED", "$30,504.33", "29.7%", "neutral"],
  ["WIN RATE (7D)", "68.4%", "13W / 6L", "neutral"],
  ["PROFIT FACTOR (7D)", "2.31", "2.31", "neutral"],
] as const;

const positions = [
  {
    coin: "BTC/USDT",
    symbol: "BTC",
    side: "LONG",
    strategy: "Trend Following",
    strategyLine: "Breakout",
    duration: "2h 17m",
    pnl: "+$742.18",
    pnlPct: "+1.28%",
    risk: "$1,800.00",
    riskR: "1.43R",
    entry: "67,842.50",
    current: "68,790.30",
    sl: "66,250.00",
    tp: "71,800.00",
    confidence: "0.71",
    ev: "+1.62R",
    thesis: "Breakout above 4H range high with strong volume & bullish structure.",
    invalidation: "4H close below 66,250.",
    currentPct: 28,
  },
  {
    coin: "ETH/USDT",
    symbol: "ETH",
    side: "SHORT",
    strategy: "Mean Reversion",
    strategyLine: "Pullback",
    duration: "1h 05m",
    pnl: "+$386.17",
    pnlPct: "+0.98%",
    risk: "$1,200.00",
    riskR: "1.02R",
    entry: "3,612.40",
    current: "3,547.65",
    sl: "3,670.00",
    tp: "3,410.00",
    confidence: "0.64",
    ev: "+1.28R",
    thesis: "Rejection from daily supply zone with bearish divergence on RSI.",
    invalidation: "4H close above 3,670.",
    currentPct: 28,
  },
];

const recentTrades = [
  ["12:17 UTC", "SOL/USDT", "LONG", "Momentum Continuation", "3h 42m", "+$1,152.34", "+2.31R", "Take Profit (TP1)", "profit"],
  ["11:03 UTC", "ARB/USDT", "LONG", "Breakout Retest", "1h 28m", "+$624.18", "+1.56R", "Take Profit (TP)", "profit"],
  ["09:41 UTC", "BTC/USDT", "SHORT", "Mean Reversion", "2h 11m", "+$842.21", "+1.68R", "Stop Loss", "profit"],
  ["08:22 UTC", "ETH/USDT", "LONG", "Trend Following", "5h 03m", "+$1,315.42", "+2.19R", "Take Profit (TP2)", "profit"],
  ["07:18 UTC", "MATIC/USDT", "SHORT", "Fade Strength", "1h 02m", "-$243.11", "-0.81R", "Manual Exit", "loss"],
] as const;

const decisionQueue = [
  ["12:30 UTC", "★", "AVAX/USDT", "LONG", "Breakout", "0.72", "+1.41R", "CANDIDATE", "4H range breakout, volume expanding.", "candidate"],
  ["12:29 UTC", "⌂", "LINK/USDT", "LONG", "Trend Continuation", "0.58", "+0.74R", "BLOCKED", "Daily loss limit 80% used.", "blocked"],
  ["12:27 UTC", "◉", "OP/USDT", "SHORT", "Mean Reversion", "0.66", "+1.18R", "OPENED", "Short from 4H supply zone.", "opened"],
  ["12:26 UTC", "★", "DOGE/USDT", "LONG", "Breakout Retest", "0.61", "+0.93R", "CANDIDATE", "Retest of range high as support.", "candidate"],
  ["12:24 UTC", "⌂", "ETH/USDT", "LONG", "Breakout", "0.48", "+0.42R", "BLOCKED", "R:R < 1.0 after fees.", "blocked"],
] as const;

function CoinMark({ symbol }: { symbol: string }) {
  const colors: Record<string, string> = { BTC: "#f7931a", ETH: "#627eea", SOL: "#6d5cff", ARB: "#28a0f0", MATIC: "#8247e5" };
  return <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white" style={{ background: colors[symbol] ?? "#64748b" }}>{symbol === "BTC" ? "₿" : symbol === "ETH" ? "◆" : symbol.slice(0, 1)}</span>;
}

function MetricStrip({ live }: { live?: Summary | null }) {
  const liveMetrics = live ? [
    ["EQUITY", `$${live.bankroll_usdt.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, "USDT balance", "neutral"],
    ["DAY P&L", "—", "awaiting daily series", "neutral"],
    ["UNREALIZED P&L", "—", `${live.open_positions} open positions`, "neutral"],
    ["REALIZED P&L (7D)", `$${live.total_pnl_usdt.toLocaleString("en-US", { minimumFractionDigits: 2, signDisplay: "always" })}`, `${live.roi_pct >= 0 ? "+" : ""}${live.roi_pct.toFixed(2)}% ROI`, live.total_pnl_usdt >= 0 ? "profit" : "loss"],
    ["TOTAL P&L (7D)", `$${live.total_pnl_usdt.toLocaleString("en-US", { minimumFractionDigits: 2, signDisplay: "always" })}`, `${live.roi_pct >= 0 ? "+" : ""}${live.roi_pct.toFixed(2)}%`, live.total_pnl_usdt >= 0 ? "profit" : "loss"],
    ["BUYING POWER", "—", "exchange-backed", "neutral"], ["MARGIN USED", "—", "exchange-backed", "neutral"],
    ["WIN RATE (7D)", `${live.win_rate_pct.toFixed(1)}%`, `${live.total_trades} total trades`, "neutral"], ["PROFIT FACTOR (7D)", "—", "available in Journal", "neutral"],
  ] as const : metrics;
  return (
    <section className="grid min-w-[980px] grid-cols-9 border-b border-[#202b35] bg-[#080d12] px-4 py-5">
      {liveMetrics.map(([label, value, sub, tone], index) => (
        <div key={label} className={`border-r border-[#202b35] px-4 first:pl-1 last:border-r-0 ${index === 0 ? "border-t-2 border-t-[#3186ff]" : ""}`}>
          <div className="mb-2 text-[11px] font-medium tracking-[0.01em] text-[#9aa6b3]">{label}</div>
          <div className={`font-mono text-[17px] font-medium leading-none ${tone === "profit" ? "text-[#36d477]" : "text-[#e6edf3]"}`}>{value}</div>
          <div className="mt-2 font-mono text-[12px] text-[#b4bec8]">{sub}</div>
        </div>
      ))}
    </section>
  );
}

function ExposureRiskBand() {
  return (
    <section className="grid min-w-[980px] grid-cols-[1.15fr_1.2fr_1.15fr] border-b border-[#202b35] px-4 py-4 text-[12px]">
      <div className="border-r border-[#202b35] pr-6">
        <h2 className="mb-4 text-[12px] font-medium text-[#c4cdd6]">EXPOSURE &amp; RISK</h2>
        <div className="grid grid-cols-4 gap-4">
          {[["GROSS EXPOSURE", "$60,632.18", "58.9%"], ["NET EXPOSURE", "$23,972.14", "23.3% Long"], ["MAX DAILY LOSS", "$5,000.00", "5.00%"], ["DAILY LOSS USED", "$1,092.24", "2.18%"]].map(([label, value, sub]) => (
            <div key={label}>
              <div className="mb-2 text-[10px] text-[#8f9aa5]">{label}</div>
              <div className={`font-mono text-[15px] ${label === "DAILY LOSS USED" ? "text-[#36d477]" : "text-[#e6edf3]"}`}>{value}</div>
              <div className={`mt-1 font-mono text-[11px] ${label === "DAILY LOSS USED" ? "text-[#36d477]" : "text-[#b2bcc6]"}`}>{sub}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="border-r border-[#202b35] px-6">
        <h2 className="mb-4 text-[12px] font-medium text-[#c4cdd6]">EXPOSURE BY COIN (ΔI)</h2>
        <div className="flex items-end gap-4">
          {[['BTC', '31.2%', 100], ['ETH', '17.6%', 58], ['SOL', '6.9%', 24], ['ARB', '3.2%', 12], ['OTH', '5.0%', 18]].map(([coin, value, width]) => (
            <div key={String(coin)} className="min-w-0 flex-1">
              <div className="mb-2 text-[12px] text-[#d7dee5]">{coin}</div>
              <div className="font-mono text-[14px] text-[#e6edf3]">{value}</div>
              <div className="mt-3 h-1 rounded-sm bg-[#1b2935]"><div className="h-full rounded-sm bg-[#2e8bff]" style={{ width: `${Number(width)}%` }} /></div>
            </div>
          ))}
        </div>
      </div>
      <div className="pl-6">
        <h2 className="mb-4 text-[12px] font-medium text-[#c4cdd6]">RISK METRICS</h2>
        <div className="grid grid-cols-5 gap-4">
          {[['PORTFOLIO VaR (95%)', '$2,898.74', '2.82%'], ['EXPECTED SHORTFALL', '$4,451.20', '4.33%'], ['SHARPE (7D)', '1.42', ''], ['MAX DRAWDOWN (7D)', '3.71%', ''], ['LEVERAGE', '1.98x', 'EFF. 1.37x']].map(([label, value, sub]) => (
            <div key={String(label)}>
              <div className="mb-2 whitespace-nowrap text-[10px] text-[#8f9aa5]">{label}</div>
              <div className={`font-mono text-[15px] ${label === 'MAX DRAWDOWN (7D)' ? 'text-[#ff4d54]' : 'text-[#e6edf3]'}`}>{value}</div>
              <div className="mt-1 font-mono text-[11px] text-[#b2bcc6]">{sub}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PriceTrack({ position }: { position: (typeof positions)[number] }) {
  return (
    <div className="relative mt-2 h-5 min-w-[230px]">
      <div className="absolute left-0 right-0 top-[9px] h-px bg-[#60717e]" />
      <div className="absolute left-0 top-[7px] h-[5px] w-[18%] bg-[#c94a54]" />
      <div className="absolute left-[18%] top-[7px] h-[5px] w-[62%] bg-[#286f51]" />
      <div className="absolute left-[18%] top-0 h-5 w-px bg-[#e4ebef]" />
      <div className="absolute left-[28%] top-[5px] h-2 w-2 -translate-x-1/2 rounded-full bg-[#e4ebef]" />
      <div className="absolute left-[65%] top-[5px] h-2 w-2 -translate-x-1/2 rounded-full bg-[#2e8bff]" />
      <div className="absolute left-[90%] top-[5px] h-2 w-2 -translate-x-1/2 rounded-full bg-[#36d477]" />
      <div className="absolute left-0 top-0 h-2 w-2 -translate-x-1/2 rounded-full bg-[#ff4d54]" />
      <div className="absolute right-0 top-0 h-2 w-2 translate-x-1/2 rounded-full bg-[#36d477]" />
    </div>
  );
}

function OpenPositions() {
  return (
    <section className="min-w-[1120px] border-b border-[#202b35]">
      <div className="flex items-center justify-between border-b border-[#202b35] px-4 py-3">
        <h2 className="text-[12px] font-medium text-[#d1d9e0]">OPEN POSITIONS (2)</h2>
        <button className="text-[12px] text-[#c5cdd4]">Sort: At Risk <span className="ml-2">⌄</span></button>
      </div>
      <div className="grid grid-cols-[1.15fr_.6fr_1.1fr_.75fr_1fr_.9fr_1.2fr_1.2fr_1.2fr_1.15fr_.7fr_2fr] gap-3 border-b border-[#202b35] px-4 py-3 text-[10px] text-[#8d9aa5]">
        {['PAIR', 'SIDE', 'STRATEGY', 'DURATION', 'UNREALIZED P&L', 'RISK', 'ENTRY', 'CURRENT', 'SL', 'TP', 'CONFIDENCE', 'EXP. VALUE / THESIS'].map(label => <span key={label}>{label}</span>)}
      </div>
      {positions.map(position => (
        <div key={position.coin} className="grid grid-cols-[1.15fr_.6fr_1.1fr_.75fr_1fr_.9fr_1.2fr_1.2fr_1.2fr_1.15fr_.7fr_2fr] items-center gap-3 border-b border-[#202b35] px-4 py-4 text-[12px] last:border-b-0">
          <div className="flex items-center gap-2"><CoinMark symbol={position.symbol} /><div><div className="text-[12px] text-[#e6edf3]">{position.coin}</div><div className="mt-1 text-[11px] text-[#8996a2]">Perp</div></div></div>
          <div className={position.side === 'LONG' ? 'text-[#36d477]' : 'text-[#ff4d54]'}>{position.side}</div>
          <div className="leading-tight text-[#d9e1e8]"><div>{position.strategy}</div><div>{position.strategyLine}</div></div>
          <div className="font-mono text-[#d2dae1]">{position.duration}</div>
          <div className="font-mono text-[#36d477]"><div>{position.pnl}</div><div className="mt-1 text-[11px]">{position.pnlPct}</div></div>
          <div className="font-mono text-[#dce4ea]"><div>{position.risk}</div><div className="mt-1 text-[11px] text-[#36d477]">{position.riskR}</div></div>
          <div className="font-mono text-[#dce4ea]">{position.entry}</div>
          <div className="font-mono text-[#dce4ea]">{position.current}</div>
          <div className="font-mono text-[#dce4ea]">{position.sl}</div>
          <div className="font-mono text-[#dce4ea]"><PriceTrack position={position} /><span className="sr-only">Take profit {position.tp}</span></div>
          <div className="font-mono text-[#dce4ea]">{position.confidence}</div>
          <div className="leading-tight"><div className="font-mono text-[#36d477]">{position.ev}</div><p className="mt-2 max-w-[260px] text-[12px] leading-[1.35] text-[#dce4ea]">{position.thesis}</p><p className="mt-1 text-[12px] leading-[1.35] text-[#ff4d54]">Invalidation: {position.invalidation}</p></div>
        </div>
      ))}
    </section>
  );
}

function RecentTrades() {
  return (
    <section className="min-w-[620px] border-r border-[#202b35]">
      <div className="flex items-center justify-between border-b border-[#202b35] px-4 py-3"><h2 className="text-[12px] font-medium text-[#d1d9e0]">RECENT CLOSED TRADES</h2><a className="text-[12px] text-[#3b8cff]">View all ↗</a></div>
      <div className="grid grid-cols-[.85fr_1fr_.7fr_1.5fr_.7fr_1fr_.7fr_1.3fr] gap-3 border-b border-[#202b35] px-4 py-3 text-[10px] text-[#8d9aa5]">{['CLOSED', 'PAIR', 'SIDE', 'STRATEGY', 'DURATION', 'REALIZED P&L', 'R (MULTIPLE)', 'EXIT REASON'].map(label => <span key={label}>{label}</span>)}</div>
      {recentTrades.map((trade) => <div key={trade[0]} className="grid grid-cols-[.85fr_1fr_.7fr_1.5fr_.7fr_1fr_.7fr_1.3fr] gap-3 border-b border-[#202b35] px-4 py-3 text-[12px] last:border-b-0"><span className="font-mono text-[#c5ced7]">{trade[0]}</span><span>{trade[1]}</span><span className={trade[2] === 'LONG' ? 'text-[#36d477]' : 'text-[#ff4d54]'}>{trade[2]}</span><span className="leading-tight">{trade[3]}</span><span className="font-mono">{trade[4]}</span><span className={`font-mono ${trade[8] === 'loss' ? 'text-[#ff4d54]' : 'text-[#36d477]'}`}>{trade[5]}</span><span className={`font-mono ${trade[8] === 'loss' ? 'text-[#ff4d54]' : 'text-[#36d477]'}`}>{trade[6]}</span><span>{trade[7]}</span></div>)}
      <div className="px-4 py-4"><a className="text-[12px] text-[#3b8cff]">View all trades in Journal</a></div>
    </section>
  );
}

function DecisionQueue() {
  return (
    <section className="min-w-[620px]">
      <div className="flex items-center justify-between border-b border-[#202b35] px-4 py-3"><h2 className="text-[12px] font-medium text-[#d1d9e0]">AGENT DECISION QUEUE</h2><span className="text-[#566675]">›</span></div>
      <div className="grid grid-cols-[.8fr_.45fr_1fr_.65fr_1.35fr_.55fr_.7fr_.85fr_2fr] gap-3 border-b border-[#202b35] px-4 py-3 text-[10px] text-[#8d9aa5]">{['TIME', 'TYPE', 'CANDIDATE', 'SIDE', 'STRATEGY', 'CONF.', 'EXP. VALUE', 'STATUS', 'REASON / NOTES'].map(label => <span key={label}>{label}</span>)}</div>
      {decisionQueue.map((event) => <div key={event[0] + event[2]} className="grid grid-cols-[.8fr_.45fr_1fr_.65fr_1.35fr_.55fr_.7fr_.85fr_2fr] gap-3 border-b border-[#202b35] px-4 py-3 text-[12px] last:border-b-0"><span className="font-mono text-[#c5ced7]">{event[0]}</span><span className={`text-[18px] leading-none ${event[9] === 'blocked' ? 'text-[#ff4d54]' : event[9] === 'opened' ? 'text-[#36d477]' : 'text-[#3b8cff]'}`}>{event[1]}</span><span>{event[2]}</span><span className={event[3] === 'LONG' ? 'text-[#36d477]' : 'text-[#ff4d54]'}>{event[3]}</span><span className="leading-tight">{event[4]}</span><span className="font-mono">{event[5]}</span><span className="font-mono text-[#36d477]">{event[6]}</span><span className={event[9] === 'blocked' ? 'text-[#ff4d54]' : event[9] === 'opened' ? 'text-[#36d477]' : 'text-[#3b8cff]'}>{event[7]}</span><span className="leading-tight text-[#dce4ea]">{event[8]}</span></div>)}
      <div className="px-4 py-4 text-right"><a className="text-[12px] text-[#3b8cff]">View full log</a></div>
    </section>
  );
}

export default function Page() {
  const [halted, setHalted] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => Promise.all([api.summary(), api.agentStatus()]).then(([nextSummary, nextAgent]) => {
      if (!active) return;
      setSummary(nextSummary);
      setAgent(nextAgent);
      setHalted(Boolean(nextSummary.kill_switch_active));
    }).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  return (
    <div className="min-h-screen min-w-[1486px] bg-[#080d12] font-sans text-[#e6edf3] selection:bg-[#174d82]">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-[186px] flex-col border-r border-[#202b35] bg-[#0b1117]">
        <div className="flex h-[58px] items-center border-b border-[#202b35] px-5"><div className="text-[20px] font-semibold tracking-[-0.04em] text-[#dfe7ee]">Trading<span className="text-[#3b8cff]">AI</span></div></div>
        <nav className="pt-4">
          {navItems.map(({ label, icon: Icon }) => {
            const active = label === "Dashboard";
            return <a key={label} href="#" className={`flex h-[48px] items-center gap-3 border-l-2 px-5 text-[13px] transition-colors ${active ? "border-[#2e8bff] bg-[#101c29] text-[#3b8cff]" : "border-transparent text-[#c3cdd6] hover:bg-[#10171f]"}`}><Icon size={20} weight={active ? "fill" : "regular"} />{label}</a>;
          })}
        </nav>
        <div className="mt-auto border-t border-[#202b35] px-5 py-5"><div className="flex items-center gap-2 text-[12px] text-[#36d477]"><span className="h-2 w-2 rounded-full bg-[#36d477]" />Main Account <span className="ml-auto text-[#9aa6b3]">⌄</span></div><div className="mt-3 pl-4 font-mono text-[11px] text-[#778692]">0x5a7b...23f1</div></div>
      </aside>

      <header className="fixed left-[186px] right-0 top-0 z-20 flex h-[58px] items-center justify-between border-b border-[#202b35] bg-[#080d12] px-6">
        <div className="flex items-center gap-5 text-[13px]"><span className="border border-[#2e3e4d] px-4 py-2 font-medium text-[#3b8cff]">{agent?.testnet === false ? "LIVE" : "TESTNET"}</span><span className={`flex items-center gap-2 ${agent?.trading_agent === "ok" ? "text-[#36d477]" : "text-[#e5b638]"}`}><span className="h-2 w-2 rounded-full bg-current" />{agent?.trading_agent === "ok" ? "Agent Live" : "Agent checking"}</span><span className="h-5 w-px bg-[#334452]" /><span className="text-[#c2ccd5]">Last data sync: <span className="font-mono text-[#dfe7ee]">{agent ? new Date(agent.checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) : "—"} UTC</span></span></div>
        <button onClick={() => setHalted(value => !value)} className={`border px-4 py-2 text-[12px] font-semibold transition-colors ${halted ? "border-[#36d477] text-[#36d477]" : "border-[#ff4d54] text-[#ff4d54] hover:bg-[#2b1419]"}`}><span className="mr-2">{halted ? "▶" : "Ⅱ"}</span>{halted ? "Resume entries" : "Halt entries"}</button>
      </header>

      <main className="ml-[186px] min-w-[1486px] overflow-x-auto pt-[58px]">
        <MetricStrip live={summary} />
        <ExposureRiskBand />
        <OpenPositions />
        <div className="grid min-w-[1240px] grid-cols-2"><RecentTrades /><DecisionQueue /></div>
        <footer className="flex min-w-[980px] items-center justify-between border-t border-[#202b35] px-4 py-3 text-[11px] text-[#8f9aa5]"><div className="flex gap-8"><span>Server: <b className="font-normal text-[#36d477]">ok</b></span><span>Data Feed: <b className="font-normal text-[#36d477]">ok</b></span><span>Latency: <b className="font-normal text-[#dbe3e9]">112ms</b></span></div><span>Time: 12:31:04 UTC</span></footer>
      </main>
    </div>
  );
}
