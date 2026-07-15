"use client";

import { useEffect, useMemo, useState } from "react";
import { DownloadSimple, MagnifyingGlass, Pause, Play, X } from "@phosphor-icons/react";
import { api, ActivityLogEntry } from "@/lib/api";

type Status = "INFO" | "CANDIDATE" | "BLOCKED" | "OPENED";

const statusFilters = ["ALL", "INFO", "CANDIDATE", "BLOCKED", "OPENED"] as const;

const statusStyles: Record<Status, string> = {
  INFO: "text-[#55b8ff]",
  CANDIDATE: "text-[#b27aff]",
  BLOCKED: "text-[#ff4d55]",
  OPENED: "text-[#37dc7a]",
};

function levelToStatus(level: string | null): Status {
  if (level === "open") return "OPENED";
  if (level === "block") return "BLOCKED";
  if (level === "candidate") return "CANDIDATE";
  return "INFO";
}

function StatusLabel({ status }: { status: Status }) {
  return <span className={`inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold tracking-wide ${statusStyles[status]}`}><i className="h-1.5 w-1.5 rounded-full bg-current" />{status}</span>;
}

function Inspector({ entry, onClose }: { entry: ActivityLogEntry | null; onClose: () => void }) {
  if (!entry) return <aside className="flex min-h-0 flex-col items-center justify-center border-l border-[#172532] bg-[#050b10] p-6 text-center text-[11px] text-[#7b8d99]">Select an entry to see details.</aside>;
  return (
    <aside className="flex min-h-0 flex-col border-l border-[#172532] bg-[#050b10]">
      <div className="flex h-[46px] items-center justify-between border-b border-[#172532] px-4">
        <span className="text-[11px] font-semibold tracking-[.11em] text-[#a7b4c1]">SELECTED EVENT</span>
        <button onClick={onClose} className="text-[#a7b4c1]" aria-label="Close inspector"><X size={18} /></button>
      </div>
      <div className="overflow-auto px-4 py-4">
        <div className="flex items-center justify-between border-b border-[#172532] pb-3">
          <StatusLabel status={levelToStatus(entry.level)} />
          <span className="font-mono text-[10px] text-[#8594a3]">ID: {entry.id}</span>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 py-4 text-[11px]">
          <div><dt className="text-[#778796]">Time (UTC)</dt><dd className="mt-1 font-mono text-[#dbe3eb]">{new Date(entry.created_at).toLocaleTimeString([], { hour12: false })}</dd></div>
          <div><dt className="text-[#778796]">Coin</dt><dd className="mt-1 font-mono text-[#dbe3eb]">{entry.symbol ?? "—"}</dd></div>
          <div><dt className="text-[#778796]">Cycle</dt><dd className="mt-1 font-mono text-[#dbe3eb]">{entry.cycle ?? "—"}</dd></div>
        </dl>
        <section className="border-t border-[#172532] pt-4">
          <h3 className="mb-3 text-[11px] font-semibold tracking-[.11em] text-[#a7b4c1]">MESSAGE</h3>
          <p className="text-[12px] leading-[1.6] text-[#dbe3eb]">{entry.message}</p>
        </section>
      </div>
    </aside>
  );
}

export default function LiveLogPage() {
  const [filter, setFilter] = useState<(typeof statusFilters)[number]>("ALL");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);
  const [liveEvents, setLiveEvents] = useState<ActivityLogEntry[]>([]);
  const [apiUnavailable, setApiUnavailable] = useState(false);

  useEffect(() => {
    if (paused) return;
    let active = true;
    const load = () => api.activityLog(200).then((entries) => {
      if (!active) return;
      setLiveEvents(entries);
      setApiUnavailable(false);
    }).catch(() => { if (active) setApiUnavailable(true); });
    load();
    const timer = window.setInterval(load, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, [paused]);

  const filtered = useMemo(() => liveEvents.filter((entry) =>
    (filter === "ALL" || levelToStatus(entry.level) === filter) &&
    `${entry.symbol ?? ""} ${entry.message}`.toLowerCase().includes(query.toLowerCase())
  ), [filter, query, liveEvents]);

  const selected = filtered.find((e) => e.id === selectedId) ?? null;

  const counts = useMemo(() => ({
    scanned: liveEvents.length,
    candidates: liveEvents.filter((e) => levelToStatus(e.level) === "CANDIDATE").length,
    blocked: liveEvents.filter((e) => levelToStatus(e.level) === "BLOCKED").length,
    opened: liveEvents.filter((e) => levelToStatus(e.level) === "OPENED").length,
  }), [liveEvents]);

  return (
    <div className="min-h-screen min-w-[1150px] bg-[#03070b] font-sans text-[#dce5ed]">
      <main className="flex min-h-screen flex-col">
        <header className="flex h-[58px] items-center justify-between border-b border-[#172532] px-7">
          <div className="flex items-center gap-3">
            <h1 className="text-[21px] font-semibold tracking-[-.02em]">Live Log</h1>
            <span className={`flex items-center gap-1.5 text-[11px] ${paused ? "text-[#eab52e]" : "text-[#35db79]"}`}><i className="h-2 w-2 rounded-full bg-current" />{paused ? "PAUSED" : "LIVE"}</span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-[#aebdca]">
            <button onClick={() => setPaused(!paused)} className="grid h-8 w-8 place-items-center border border-[#3a4b58] bg-[#0b1219] text-[#d5dfe8]" aria-label={paused ? "Resume stream" : "Pause stream"}>{paused ? <Play size={15} /> : <Pause size={15} />}</button>
            <label className="flex h-8 w-[180px] items-center gap-2 border border-[#263744] bg-[#0a1117] px-2 text-[#778795]">
              <MagnifyingGlass size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-[11px] text-[#dce5ed] outline-none" placeholder="Search logs..." />
            </label>
          </div>
        </header>
        <div className="px-[15px] pt-[12px]">
          <div className="flex h-[59px] items-center border border-[#1c303d] bg-[#071017]">
            {[["SCANNED", counts.scanned], ["CANDIDATES", counts.candidates], ["BLOCKED", counts.blocked], ["OPENED", counts.opened]].map(([label, value]) => (
              <div key={label} className="flex h-[38px] min-w-[86px] flex-col justify-center border-r border-[#1c303d] px-3">
                <span className={`text-[9px] font-semibold tracking-[.12em] ${label === "BLOCKED" ? "text-[#ff4d55]" : label === "OPENED" ? "text-[#40de7e]" : "text-[#8ea0af]"}`}>{label}</span>
                <strong className={`font-mono text-[16px] ${label === "BLOCKED" ? "text-[#ff4d55]" : label === "OPENED" ? "text-[#40de7e]" : "text-[#dce5ed]"}`}>{value}</strong>
              </div>
            ))}
            <div className="ml-auto flex items-center gap-2 px-3">
              {statusFilters.map((item) => (
                <button key={item} onClick={() => setFilter(item)} className={`h-7 border px-3 text-[10px] font-semibold tracking-wide ${filter === item ? "border-[#278fff] bg-[#0c2b48] text-[#75c3ff]" : "border-[#20313d] bg-[#09141b] text-[#8c9aa7]"}`}>{item}</button>
              ))}
            </div>
          </div>
          {apiUnavailable && <div className="mt-2 border border-[#765b20] bg-[#2a220f] px-3 py-2 text-[11px] text-[#eab83c]">Live log API unavailable.</div>}
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_360px] gap-[18px] px-[15px] pb-[15px] pt-[12px]">
          <section className="min-w-0 border border-[#172b38] bg-[#040a0f]">
            <div className="grid h-9 grid-cols-[110px_105px_108px_minmax(320px,1fr)] items-center border-b border-[#1b303d] px-3 text-[10px] font-semibold tracking-[.13em] text-[#92a1ae]">
              <span>TIME (UTC)</span><span>COIN</span><span>STATUS</span><span>MESSAGE</span>
            </div>
            <div>
              {filtered.length ? filtered.map((entry) => (
                <button key={entry.id} onClick={() => setSelectedId(entry.id)} className={`grid min-h-[34px] w-full grid-cols-[110px_105px_108px_minmax(320px,1fr)] items-center border-b border-[#142630] px-3 text-left text-[11px] hover:bg-[#0a1a25] ${selectedId === entry.id ? "bg-[#082238] outline outline-1 outline-[#238ee9] outline-offset-[-1px]" : ""}`}>
                  <span className="font-mono text-[#9baab7]">{new Date(entry.created_at).toLocaleTimeString([], { hour12: false })}</span>
                  <span className="font-mono text-[#d2dce5]">{entry.symbol ?? "—"}</span>
                  <StatusLabel status={levelToStatus(entry.level)} />
                  <span className="truncate text-[#d2dce5]">{entry.message}</span>
                </button>
              )) : <div className="p-6 text-center text-[11px] text-[#7b8d99]">No log entries yet.</div>}
            </div>
            <footer className="flex h-12 items-center px-3 text-[11px] text-[#8696a4]">Showing {filtered.length} of {liveEvents.length} events</footer>
          </section>
          <Inspector entry={selected} onClose={() => setSelectedId(null)} />
        </div>
      </main>
    </div>
  );
}
