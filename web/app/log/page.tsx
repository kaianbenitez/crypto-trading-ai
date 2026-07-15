"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bell,
  BookOpen,
  Broadcast,
  ChartLineUp,
  Code,
  DownloadSimple,
  Eye,
  GearSix,
  House,
  MagnifyingGlass,
  Monitor,
  Pause,
  Play,
  ShieldWarning,
  ShoppingCart,
  SignOut,
  SquaresFour,
  Strategy,
  X,
} from "@phosphor-icons/react";
import { api } from "@/lib/api";

type Status = "INFO" | "CANDIDATE" | "BLOCKED" | "OPENED" | "UPDATED" | "CLOSED" | "ERROR";

type LogEvent = {
  id: string;
  time: string;
  coin: string;
  stage: string;
  status: Status;
  confidence: string;
  reason: string;
  duration: string;
};

const events: LogEvent[] = [
  { id: "e9f7c3b1", time: "12:45:21.842", coin: "SOL/USDT", stage: "Signal Generation", status: "CANDIDATE", confidence: "72% / +1.42R", reason: "Breakout above 4H range + RSI>55 + Vol spike", duration: "412ms" },
  { id: "e9f7c3a8", time: "12:45:21.631", coin: "SOL/USDT", stage: "Shortlist", status: "CANDIDATE", confidence: "—", reason: "Top momentum 4H | Score: 86", duration: "184ms" },
  { id: "e9f7c39f", time: "12:45:21.102", coin: "SOL/USDT", stage: "Market Scan", status: "INFO", confidence: "—", reason: "Volume > 100K USDT, Vol 24h > 15%", duration: "1.28s" },
  { id: "e9f7c398", time: "12:45:20.998", coin: "SOL/USDT", stage: "Regime Check", status: "INFO", confidence: "Trending Bull", reason: "Regime: Trending Bull (Score: 0.78)", duration: "236ms" },
  { id: "e9f7c391", time: "12:45:20.875", coin: "SOL/USDT", stage: "MTF Gate", status: "INFO", confidence: "Pass", reason: "Aligned: 1H/4H/D Bullish", duration: "143ms" },
  { id: "e9f7c38a", time: "12:45:20.742", coin: "SOL/USDT", stage: "Cost Gate", status: "INFO", confidence: "Pass", reason: "Est. cost: 0.00027 (0.008%) < Max 0.02%", duration: "91ms" },
  { id: "e9f7c383", time: "12:45:20.661", coin: "SOL/USDT", stage: "Risk Cap Check", status: "INFO", confidence: "Pass", reason: "Portfolio risk: 0.78% < Max 2.50%", duration: "88ms" },
  { id: "e9f7c37b", time: "12:45:20.501", coin: "DOGE/USDT", stage: "Signal Generation", status: "BLOCKED", confidence: "38% / -0.21R", reason: "Weak momentum, RSI<50", duration: "311ms" },
  { id: "e9f7c372", time: "12:45:20.210", coin: "ADA/USDT", stage: "Signal Generation", status: "BLOCKED", confidence: "41% / -0.05R", reason: "Blocked by regime filter", duration: "207ms" },
  { id: "e9f7c36c", time: "12:45:19.872", coin: "SOL/USDT", stage: "Order Placement", status: "OPENED", confidence: "72% / +1.42R", reason: "Market buy: 0.500 SOL @ 148.32", duration: "642ms" },
  { id: "e9f7c364", time: "12:45:19.211", coin: "SOL/USDT", stage: "Stop Protection", status: "OPENED", confidence: "—", reason: "Initial stop set @ 143.20 (ATR × 1.6)", duration: "97ms" },
  { id: "e9f7c35d", time: "12:45:18.542", coin: "SOL/USDT", stage: "Position Management", status: "UPDATED", confidence: "—", reason: "Trail activated: 1.8 ATR | New stop: 146.10", duration: "156ms" },
  { id: "e9f7c355", time: "12:45:16.221", coin: "SOL/USDT", stage: "Position Management", status: "UPDATED", confidence: "—", reason: "Partial take profit 1: 25% @ 152.80 (+3.0R)", duration: "129ms" },
  { id: "e9f7c34d", time: "12:45:12.884", coin: "SOL/USDT", stage: "Position Management", status: "UPDATED", confidence: "—", reason: "Breakeven stop moved to 148.35", duration: "111ms" },
  { id: "e9f7c344", time: "12:44:58.331", coin: "SOL/USDT", stage: "Position Management", status: "CLOSED", confidence: "—", reason: "Take profit 2 hit @ 156.40 (+6.1R)", duration: "178ms" },
  { id: "e9f7c33b", time: "12:44:33.117", coin: "BTC/USDT", stage: "Signal Generation", status: "BLOCKED", confidence: "33% / -0.42R", reason: "RR < 1.0 after costs", duration: "265ms" },
  { id: "e9f7c331", time: "12:44:28.903", coin: "ETH/USDT", stage: "Order Placement", status: "ERROR", confidence: "—", reason: "Exchange error: insufficient balance", duration: "812ms" },
  { id: "e9f7c329", time: "12:44:28.731", coin: "ETH/USDT", stage: "Order Placement", status: "INFO", confidence: "—", reason: "Retrying with reduced size", duration: "94ms" },
  { id: "e9f7c320", time: "12:44:28.102", coin: "ETH/USDT", stage: "Risk Cap Check", status: "BLOCKED", confidence: "—", reason: "Would exceed max position size", duration: "75ms" },
  { id: "e9f7c317", time: "12:44:27.662", coin: "XRP/USDT", stage: "Market Scan", status: "INFO", confidence: "—", reason: "Volume > 100K USDT, Vol 24h > 15%", duration: "1.11s" },
];

const statusFilters = ["ALL", "INFO", "CANDIDATE", "BLOCKED", "OPENED", "UPDATED", "CLOSED", "ERROR"] as const;

const navItems = [
  ["Overview", House], ["Dashboard", SquaresFour], ["Markets", ChartLineUp], ["Signals", Broadcast],
  ["Positions", BookOpen], ["Orders", ShoppingCart], ["Risk", ShieldWarning], ["Strategies", Strategy],
  ["Backtests", ChartLineUp], ["Live Log", Broadcast], ["Alerts", Bell], ["Config", GearSix], ["API", Code], ["System", Monitor],
] as const;

const statusStyles: Record<Status, string> = {
  INFO: "text-[#55b8ff]",
  CANDIDATE: "text-[#b27aff]",
  BLOCKED: "text-[#ff4d55]",
  OPENED: "text-[#37dc7a]",
  UPDATED: "text-[#ffb52b]",
  CLOSED: "text-[#aab4c0]",
  ERROR: "text-[#ff4d55]",
};

function StatusLabel({ status }: { status: Status }) {
  return <span className={`inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold tracking-wide ${statusStyles[status]}`}><i className="h-1.5 w-1.5 rounded-full bg-current" />{status}</span>;
}

function Sidebar() {
  return <aside className="fixed inset-y-0 left-0 z-20 flex w-[142px] flex-col border-r border-[#17222c] bg-[#050a0f] text-[#bac6d2]">
    <div className="flex h-[58px] items-center gap-2 border-b border-[#17222c] px-3">
      <span className="grid h-[22px] w-[22px] place-items-center rounded-[4px] border border-[#2697ff] text-[11px] font-bold text-[#5db6ff]">AI</span>
      <span className="text-[16px] font-semibold tracking-[-.02em] text-[#e7edf4]">Trading<span className="text-[#38a5ff]">AI</span></span>
    </div>
    <nav className="flex-1 py-3">
      {navItems.map(([label, Icon]) => <div key={label} className={`flex h-[42px] items-center gap-3 border-l-2 px-3 text-[12px] ${label === "Live Log" ? "border-[#2697ff] bg-[#0d263b] text-[#67b9ff]" : "border-transparent text-[#a9b6c3]"}`}><Icon size={18} weight={label === "Live Log" ? "fill" : "regular"} />{label}</div>)}
    </nav>
    <div className="border-t border-[#17222c] px-3 py-4 text-[11px] text-[#8d9aaa]">
      <div className="flex items-center gap-2 text-[#d5dce4]"><i className="h-2 w-2 rounded-full bg-[#2fdf78]" />Connected</div>
      <div className="mt-2">v1.6.3</div>
      <div className="mt-4 flex items-center justify-between"><span>Session</span><SignOut size={16} /></div>
    </div>
  </aside>;
}

function Inspector({ event, onClose }: { event: LogEvent; onClose: () => void }) {
  const path = [
    ["Market Scan", "12:45:21.102", "INFO"], ["Shortlist", "12:45:21.631", "CANDIDATE"], ["Signal Generation", "12:45:21.842", "CANDIDATE"],
    ["Regime Check", "12:45:20.998", "INFO"], ["MTF Gate", "12:45:20.875", "INFO"], ["Cost Gate", "12:45:20.742", "INFO"],
    ["Risk Cap Check", "12:45:20.661", "INFO"], ["Order Placement", "—", "—"], ["Stop Protection", "—", "—"], ["Position Management", "—", "—"],
  ];
  const modules = [
    ["Regime", "Trending Bull (0.78)"], ["Trend (1H/4H/D)", "Bull/Bull/Bull"], ["Momentum", "Strong (72)"], ["Volatility", "1.24% (High)"],
    ["Volume", "182% of 20d avg"], ["Liquidity", "High"], ["Spread", "0.008%"], ["Est. Cost", "0.00027 (0.008%)"], ["Risk (Portfolio)", "0.78%"],
  ];
  return <aside className="flex min-h-0 flex-col border-l border-[#172532] bg-[#050b10]">
    <div className="flex h-[46px] items-center justify-between border-b border-[#172532] px-4"><span className="text-[11px] font-semibold tracking-[.11em] text-[#a7b4c1]">SELECTED EVENT</span><button onClick={onClose} className="text-[#a7b4c1]" aria-label="Close inspector"><X size={18} /></button></div>
    <div className="overflow-auto px-4 py-4">
      <div className="flex items-center justify-between border-b border-[#172532] pb-3"><div className="flex items-center gap-3"><span className="rounded border border-[#633f9c] bg-[#24143e] px-2 py-1 text-[10px] font-semibold text-[#bd8cff]">CANDIDATE</span><span className="text-[12px] text-[#b6c1cc]">Signal Generation</span></div><span className="font-mono text-[10px] text-[#8594a3]">ID: {event.id} □</span></div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 py-4 text-[11px]"><div><dt className="text-[#778796]">Time (UTC)</dt><dd className="mt-1 font-mono text-[#dbe3eb]">{event.time}</dd></div><div><dt className="text-[#778796]">Coin</dt><dd className="mt-1 font-mono text-[#dbe3eb]">{event.coin}</dd></div><div><dt className="text-[#778796]">Confidence / EV</dt><dd className="mt-1 font-mono text-[#dbe3eb]">{event.confidence}</dd></div><div><dt className="text-[#778796]">Duration</dt><dd className="mt-1 font-mono text-[#dbe3eb]">{event.duration}</dd></div><div><dt className="text-[#778796]">Strategy</dt><dd className="mt-1 text-[#dbe3eb]">Breakout Momentum v2.3</dd></div><div><dt className="text-[#778796]">Run ID</dt><dd className="mt-1 font-mono text-[#dbe3eb]">run_2025-05-21_12:45:00</dd></div><div><dt className="text-[#778796]">Cycle</dt><dd className="mt-1 font-mono text-[#dbe3eb]">Cycle #821</dd></div></dl>
      <section className="border-t border-[#172532] pt-4"><h3 className="mb-3 text-[11px] font-semibold tracking-[.11em] text-[#a7b4c1]">DECISION PATH</h3><div className="relative pl-5 before:absolute before:bottom-2 before:left-[5px] before:top-2 before:w-px before:bg-[#2a4150]">{path.map(([name, time, status], index) => <div key={name} className={`relative flex min-h-[28px] items-center justify-between gap-2 text-[11px] ${index === 2 ? "rounded bg-[#27153e] px-2 -ml-2" : ""}`}><i className={`absolute -left-[19px] h-2.5 w-2.5 rounded-full border-2 border-[#050b10] ${status === "CANDIDATE" ? "bg-[#a56cff]" : status === "INFO" ? "bg-[#54b6ff]" : "bg-[#3d4d58]"}`} /><span className="text-[#c7d0d9]">{name}</span><span className={`font-mono text-[10px] ${status === "—" ? "text-[#596875]" : statusStyles[status as Status]}`}>{status} <em className="ml-2 not-italic text-[#83929f]">{time}</em></span></div>)}</div></section>
      <section className="mt-4 border-t border-[#172532] pt-4"><h3 className="mb-3 text-[11px] font-semibold tracking-[.11em] text-[#a7b4c1]">OBSERVED VS APPLIED MODULES</h3><div className="overflow-hidden border border-[#1a2c38]"><div className="grid grid-cols-[1fr_1fr_1fr] bg-[#0b151d] px-2 py-2 text-[10px] text-[#8595a3]"><span>MODULE</span><span>OBSERVED</span><span>APPLIED</span></div>{modules.map(([name, value]) => <div key={name} className="grid grid-cols-[1fr_1fr_1fr] border-t border-[#172532] px-2 py-2 text-[10px]"><span className="text-[#aebbc7]">{name}</span><span className="text-[#4ee28a]">{value}</span><span className="text-[#4ee28a]">{value}</span></div>)}</div></section>
      <div className="mt-4 flex gap-2"><button className="flex-1 border border-[#2c4659] bg-[#0b151d] px-3 py-2 text-[11px] text-[#d9e3ec]">View Signal Details</button><button className="flex-1 border border-[#258dff] bg-[#09233a] px-3 py-2 text-[11px] text-[#72c1ff]">View Position ({event.coin})</button></div>
    </div>
  </aside>;
}

export default function LiveLogPage() {
  const [filter, setFilter] = useState<(typeof statusFilters)[number]>("ALL");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(events[0].id);
  const [paused, setPaused] = useState(false);
  const [liveEvents, setLiveEvents] = useState(events);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  useEffect(() => {
    if (paused) return;
    let active = true;
    const load = () => api.activityLog(200).then((entries) => {
      if (!active || !entries.length) return;
      const mapped = entries.map((entry, index) => ({
        id: `live-${entry.id}`,
        time: new Date(entry.created_at).toLocaleTimeString([], { hour12: false, fractionalSecondDigits: 3 }),
        coin: entry.symbol ?? "—",
        stage: "Agent Decision",
        status: (entry.level === "open" ? "OPENED" : entry.level === "block" ? "BLOCKED" : entry.level === "candidate" ? "CANDIDATE" : "INFO") as Status,
        confidence: "—",
        reason: entry.message,
        duration: "—",
      }));
      setLiveEvents(mapped);
      setSelectedId(mapped[0].id);
      setApiUnavailable(false);
    }).catch(() => { if (active) setApiUnavailable(true); });
    load();
    const timer = window.setInterval(load, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, [paused]);
  const filtered = useMemo(() => liveEvents.filter((event) => (filter === "ALL" || event.status === filter) && `${event.coin} ${event.stage} ${event.reason}`.toLowerCase().includes(query.toLowerCase())), [filter, query, liveEvents]);
  const selected = liveEvents.find((event) => event.id === selectedId) ?? liveEvents[0];

  return <div className="min-h-screen min-w-[1530px] bg-[#03070b] font-sans text-[#dce5ed]">
    <Sidebar />
    <main className="ml-[142px] flex min-h-screen flex-col">
      <header className="flex h-[58px] items-center justify-between border-b border-[#172532] px-7"><div className="flex items-center gap-3"><h1 className="text-[21px] font-semibold tracking-[-.02em]">Live Log</h1><span className="flex items-center gap-1.5 text-[11px] text-[#35db79]"><i className="h-2 w-2 rounded-full bg-current" />LIVE</span></div><div className="flex items-center gap-3 text-[11px] text-[#aebdca]"><span className="flex items-center gap-1.5 text-[#4ee28a]"><i className="h-2 w-2 rounded-full bg-current" />Connected</span><span className="text-[#526471]">|</span><span>Stream: Live</span><span className="text-[#526471]">|</span><span>Latency: 182ms</span><button onClick={() => setPaused(!paused)} className="ml-2 grid h-8 w-8 place-items-center border border-[#3a4b58] bg-[#0b1219] text-[#d5dfe8]" aria-label={paused ? "Resume stream" : "Pause stream"}>{paused ? <Play size={15} /> : <Pause size={15} />}</button><button className="flex h-8 items-center gap-2 border border-[#3a4b58] bg-[#0b1219] px-3 text-[#d5dfe8]"><DownloadSimple size={15} />Export</button><label className="flex h-8 w-[155px] items-center gap-2 border border-[#263744] bg-[#0a1117] px-2 text-[#778795]"><MagnifyingGlass size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-[11px] text-[#dce5ed] outline-none" placeholder="Search logs..." /><kbd className="border border-[#32404b] px-1 text-[10px]">/</kbd></label></div></header>
      <div className="px-[15px] pt-[12px]"><div className="flex h-[59px] items-center border border-[#1c303d] bg-[#071017]"><div className="flex h-full items-center gap-4 border-r border-[#1c303d] px-4 text-[11px] text-[#a9b8c5]"><span>Last Cycle (26.2s)</span></div>{[["SCANNED", String(liveEvents.length)], ["SHORTLISTED", "28"], ["CANDIDATES", String(liveEvents.filter((event) => event.status === "CANDIDATE").length)], ["BLOCKED", String(liveEvents.filter((event) => event.status === "BLOCKED").length)], ["OPENED", String(liveEvents.filter((event) => event.status === "OPENED").length)], ["UPDATED", "6"], ["CLOSED", String(liveEvents.filter((event) => event.status === "CLOSED").length)], ["ERRORS", "0"]].map(([label, value]) => <div key={label} className="flex h-[38px] min-w-[86px] flex-col justify-center border-r border-[#1c303d] px-3"><span className={`text-[9px] font-semibold tracking-[.12em] ${label === "BLOCKED" ? "text-[#ff4d55]" : label === "OPENED" ? "text-[#40de7e]" : "text-[#8ea0af]"}`}>{label}</span><strong className={`font-mono text-[16px] ${label === "BLOCKED" ? "text-[#ff4d55]" : label === "OPENED" ? "text-[#40de7e]" : "text-[#dce5ed]"}`}>{value}</strong></div>)}<div className="ml-auto flex items-center gap-2 px-3">{statusFilters.map((item) => <button key={item} onClick={() => setFilter(item)} className={`h-7 border px-3 text-[10px] font-semibold tracking-wide ${filter === item ? "border-[#278fff] bg-[#0c2b48] text-[#75c3ff]" : "border-[#20313d] bg-[#09141b] text-[#8c9aa7]"}`}>{item}</button>)}</div></div>{apiUnavailable && <div className="mt-2 border border-[#765b20] bg-[#2a220f] px-3 py-2 text-[11px] text-[#eab83c]">Live log API unavailable — showing the reference snapshot.</div>}</div>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_438px] gap-[18px] px-[15px] pb-[15px] pt-[12px]"><section className="min-w-0 border border-[#172b38] bg-[#040a0f]"><div className="grid h-9 grid-cols-[136px_105px_170px_108px_125px_minmax(320px,1fr)_78px] items-center border-b border-[#1b303d] px-3 text-[10px] font-semibold tracking-[.13em] text-[#92a1ae]"><span>TIME (UTC)</span><span>COIN</span><span>PIPELINE STAGE</span><span>STATUS</span><span>CONFIDENCE / EV</span><span>DECISION REASON</span><span>DURATION</span></div><div>{filtered.map((event) => <button key={event.id} onClick={() => setSelectedId(event.id)} className={`grid min-h-[34px] w-full grid-cols-[136px_105px_170px_108px_125px_minmax(320px,1fr)_78px] items-center border-b border-[#142630] px-3 text-left text-[11px] hover:bg-[#0a1a25] ${selectedId === event.id ? "bg-[#082238] outline outline-1 outline-[#238ee9] outline-offset-[-1px]" : ""}`}><span className="font-mono text-[#9baab7]">{event.time}</span><span className="font-mono text-[#d2dce5]">{event.coin}</span><span className="text-[#c5d0da]">{event.stage}</span><StatusLabel status={event.status} /><span className={`font-mono ${event.confidence.includes("-") ? "text-[#ff646b]" : event.confidence.includes("+") ? "text-[#4ee28a]" : "text-[#bac7d2]"}`}>{event.confidence}</span><span className="truncate text-[#d2dce5]">{event.reason}</span><span className="font-mono text-[#a2b0bc]">{event.duration}</span></button>)}</div><footer className="flex h-12 items-center justify-between px-3 text-[11px] text-[#8696a4]"><span>Showing 1–{filtered.length} of 1,246 events</span><div className="flex items-center gap-1">{["|&lt;", "&lt;", "1", "2", "3", "4", "5", "&gt;", "&gt;|"] .map((item, index) => <button key={index} className={`grid h-7 min-w-7 place-items-center border border-[#263945] px-2 font-mono ${item === "1" ? "border-[#238ee9] bg-[#0b2b48] text-[#79c4ff]" : "text-[#9aabb7]"}`} dangerouslySetInnerHTML={{ __html: item }} />)}</div></footer></section><Inspector event={selected} onClose={() => setSelectedId(events[0].id)} /></div>
    </main>
  </div>;
}
