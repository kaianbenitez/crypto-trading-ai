"use client";

import { useEffect, useMemo, useState } from "react";
import { MagnifyingGlass, X } from "@phosphor-icons/react";
import CoinLogo from "../components/CoinLogo";
import { api, CoinDigest, RosterInfo } from "@/lib/api";

type Row = { symbol: string; state: "SHORTLISTED" | "BENCHED"; benchedUntil: string | null; digest: CoinDigest | null };

const stateClass: Record<Row["state"], string> = {
  SHORTLISTED: "border-[#236448] bg-[#0b2a1c] text-[#45dd8a]",
  BENCHED: "border-[#23496e] bg-[#0c2743] text-[#55aef1]",
};

function shortSymbol(value: string) { return value.replace("/USDT:USDT", "").replace("/USDT", "").replace("USDT", ""); }
function pct(value: number | null | undefined) { return value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`; }
function price(value: number | null | undefined) { return value == null ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: value < 1 ? 6 : 2 }); }

function Detail({ row, onClose }: { row: Row | null; onClose: () => void }) {
  if (!row) return <aside className="flex min-h-0 flex-col items-center justify-center border-l border-[#1a303d] bg-[#050c12] p-6 text-center text-[11px] text-[#7b8d99]">Select a coin to see its digest.</aside>;
  const d = row.digest;
  return (
    <aside className="flex min-h-0 flex-col border-l border-[#1a303d] bg-[#050c12]">
      <div className="flex items-center justify-between border-b border-[#1a303d] px-4 py-3">
        <div className="flex items-center gap-2">
          <CoinLogo symbol={row.symbol} />
          <div>
            <div className="font-mono text-[13px] font-semibold">{row.symbol} <span className="font-normal text-[#95a4ae]">/ USDT PERP</span></div>
            <div className="text-[10px] text-[#8495a1]">Roster state: {row.state}{row.benchedUntil ? ` until ${new Date(row.benchedUntil).toLocaleString()}` : ""}</div>
          </div>
        </div>
        <button onClick={onClose} aria-label="Close coin details"><X size={18} /></button>
      </div>
      <div className="overflow-auto p-4 text-[11px]">
        {!d ? (
          <p className="text-[#8495a1]">No news digest cached for this coin yet.</p>
        ) : (
          <>
            <h3 className="mb-3 text-[10px] font-semibold tracking-[.1em] text-[#96a7b3]">24H RANGE & SENTIMENT</h3>
            <div className="grid grid-cols-2 gap-y-3">
              <div><span className="text-[#728493]">24h Low</span><strong className="mt-1 block font-mono text-[#dce5ed]">{price(d.price_low_24h)}</strong></div>
              <div><span className="text-[#728493]">24h High</span><strong className="mt-1 block font-mono text-[#dce5ed]">{price(d.price_high_24h)}</strong></div>
              <div><span className="text-[#728493]">24h Change</span><strong className={`mt-1 block font-mono ${(d.price_change_pct_24h ?? 0) >= 0 ? "text-[#45dd8a]" : "text-[#ff6167]"}`}>{pct(d.price_change_pct_24h)}</strong></div>
              <div><span className="text-[#728493]">Regime</span><strong className="mt-1 block font-mono text-[#dce5ed]">{d.regime ?? "—"}</strong></div>
              <div><span className="text-[#728493]">Watching side</span><strong className="mt-1 block font-mono text-[#dce5ed]">{d.watching_side ?? "—"}</strong></div>
              <div><span className="text-[#728493]">Sentiment</span><strong className="mt-1 block font-mono text-[#dce5ed]">{d.sentiment_label ?? "—"} ({d.sentiment_score?.toFixed(2) ?? "—"})</strong></div>
              <div><span className="text-[#728493]">Watch low</span><strong className="mt-1 block font-mono text-[#dce5ed]">{price(d.watch_low)}</strong></div>
              <div><span className="text-[#728493]">Watch high</span><strong className="mt-1 block font-mono text-[#dce5ed]">{price(d.watch_high)}</strong></div>
            </div>
            {d.headlines.length > 0 && (
              <section className="mt-5 border-t border-[#1a303d] pt-4">
                <h3 className="mb-3 text-[10px] font-semibold tracking-[.1em] text-[#96a7b3]">RECENT HEADLINES</h3>
                <ul className="space-y-2 text-[11px] text-[#c4d0d8]">{d.headlines.map((h, i) => <li key={i}>· {h}</li>)}</ul>
              </section>
            )}
            {d.summary && (
              <section className="mt-5 border-t border-[#1a303d] pt-4">
                <h3 className="mb-3 text-[10px] font-semibold tracking-[.1em] text-[#96a7b3]">SUMMARY</h3>
                <p className="text-[11px] leading-[1.5] text-[#c4d0d8]">{d.summary}</p>
              </section>
            )}
            <div className="mt-4 text-right text-[10px] text-[#7b8b97]">Digest generated: {new Date(d.created_at).toLocaleString()}</div>
          </>
        )}
      </div>
    </aside>
  );
}

export default function CoinWatchPage() {
  const [roster, setRoster] = useState<RosterInfo | null>(null);
  const [digests, setDigests] = useState<CoinDigest[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"All" | "SHORTLISTED" | "BENCHED">("All");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => Promise.all([api.roster(), api.coinDigests()])
      .then(([r, d]) => { if (active) { setRoster(r); setDigests(d); setError(null); } })
      .catch(() => active && setError("Could not load roster/coin data from the backend."));
    load();
    const timer = window.setInterval(load, 30000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const rows: Row[] = useMemo(() => {
    const digestBySymbol = new Map(digests.map((d) => [shortSymbol(d.symbol), d]));
    const active = (roster?.active ?? []).map((symbol) => ({ symbol: shortSymbol(symbol), state: "SHORTLISTED" as const, benchedUntil: null, digest: digestBySymbol.get(shortSymbol(symbol)) ?? null }));
    const benched = (roster?.benched ?? []).map((b) => ({ symbol: shortSymbol(b.symbol), state: "BENCHED" as const, benchedUntil: b.until, digest: digestBySymbol.get(shortSymbol(b.symbol)) ?? null }));
    return [...active, ...benched];
  }, [roster, digests]);

  const visible = useMemo(() => rows.filter((row) =>
    (!query || row.symbol.toLowerCase().includes(query.toLowerCase())) &&
    (status === "All" || row.state === status)
  ), [rows, query, status]);

  const selected = visible.find((r) => r.symbol === selectedSymbol) ?? visible[0] ?? null;

  return (
    <div className="min-h-screen min-w-[1150px] bg-[#03080d] text-[#dce5ed]">
      <main className="flex min-h-screen flex-col">
        <header className="flex h-[58px] items-center justify-between border-b border-[#1a2d38] px-5">
          <div>
            <h1 className="text-[19px] font-semibold">Coin Watch</h1>
            <p className="text-[10px] text-[#8395a2]">Live roster — shortlisted and benched coins</p>
          </div>
          <div className="flex items-center gap-5 text-[10px] text-[#9caeba]">
            <span>Last review: {roster?.last_review ? new Date(roster.last_review).toLocaleString() : "—"}</span>
            <span className={roster?.scan.enabled ? "text-[#45dd86]" : "text-[#e2b33d]"}>● Scan engine: {roster?.scan.status ?? "checking"}</span>
          </div>
        </header>
        {error && <div className="m-4 border border-[#765b20] bg-[#2a220f] px-3 py-2 text-[11px] text-[#eab83c]">{error}</div>}
        <div className="grid grid-cols-[minmax(0,1fr)_360px] flex-1">
          <div className="min-w-0 p-2">
            <section className="grid grid-cols-3 border border-[#172d39] bg-[#0a151d]">
              <div className="border-r border-[#172d39] px-3 py-3">
                <div className="text-[9px] font-semibold tracking-[.09em] text-[#98a9b5]">SHORTLISTED</div>
                <div className="mt-2 font-mono text-[20px] text-[#42dc83]">{roster?.active.length ?? "—"}</div>
              </div>
              <div className="border-r border-[#172d39] px-3 py-3">
                <div className="text-[9px] font-semibold tracking-[.09em] text-[#98a9b5]">BENCHED</div>
                <div className="mt-2 font-mono text-[20px] text-[#dce5ed]">{roster?.benched.length ?? "—"}</div>
              </div>
              <div className="px-3 py-3">
                <div className="text-[9px] font-semibold tracking-[.09em] text-[#98a9b5]">SCAN STATUS</div>
                <div className="mt-2 font-mono text-[20px] text-[#dce5ed]">{roster?.scan.status ?? "—"}</div>
              </div>
            </section>
            <div className="mt-3 flex items-center gap-2 border border-[#172d39] bg-[#071119] p-2">
              <label className="flex h-8 w-[200px] items-center gap-2 border border-[#293f4c] px-2 text-[10px] text-[#7e909e]">
                <MagnifyingGlass size={14} />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search coin..." className="w-full bg-transparent outline-none" />
              </label>
              <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} className="h-8 border border-[#293f4c] bg-[#0b171f] px-3 text-[10px]">
                <option value="All">All</option>
                <option value="SHORTLISTED">Shortlisted</option>
                <option value="BENCHED">Benched</option>
              </select>
            </div>
            <section className="mt-2 overflow-hidden border border-[#172d39] bg-[#071119]">
              <table className="w-full border-collapse text-[10px]">
                <thead className="bg-[#0a161e] text-left text-[9px] font-semibold tracking-[.06em] text-[#8fa0ac]">
                  <tr>{["COIN", "24H CHANGE", "REGIME", "SENTIMENT", "STATE"].map((h) => <th key={h} className="border-b border-[#1b303c] px-2 py-3">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {visible.length ? visible.map((row) => (
                    <tr key={row.symbol} onClick={() => setSelectedSymbol(row.symbol)} className={`cursor-pointer border-b border-[#152833] hover:bg-[#0d202d] ${selected?.symbol === row.symbol ? "bg-[#0c2336] outline outline-1 outline-[#248ee8] outline-offset-[-1px]" : ""}`}>
                      <td className="px-2 py-2"><span className="flex items-center gap-2 font-semibold"><CoinLogo symbol={row.symbol} />{row.symbol}</span></td>
                      <td className={`px-2 py-2 font-mono ${(row.digest?.price_change_pct_24h ?? 0) < 0 ? "text-[#ff646c]" : "text-[#d9e5ed]"}`}>{pct(row.digest?.price_change_pct_24h)}</td>
                      <td className="px-2 py-2 text-[#9daeba]">{row.digest?.regime ?? "—"}</td>
                      <td className="px-2 py-2 text-[#9daeba]">{row.digest?.sentiment_label ?? "—"}</td>
                      <td className="px-2 py-2"><span className={`rounded border px-1.5 py-1 text-[9px] font-semibold ${stateClass[row.state]}`}>{row.state}</span></td>
                    </tr>
                  )) : <tr><td colSpan={5} className="px-2 py-6 text-center text-[#7b8d99]">No coins in the current roster.</td></tr>}
                </tbody>
              </table>
              <div className="flex h-11 items-center px-3 text-[10px] text-[#81919e]">Showing {visible.length} of {rows.length} roster coins</div>
            </section>
          </div>
          <Detail row={selected} onClose={() => setSelectedSymbol(null)} />
        </div>
      </main>
    </div>
  );
}
