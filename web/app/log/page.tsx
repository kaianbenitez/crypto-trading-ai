"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import { api, ActivityLogEntry, GateStats } from "@/lib/api";

const POLL_MS = 12000;

function levelColor(level: string | null): string {
  switch (level) {
    case "open": return "var(--green)";
    case "candidate": return "var(--accent)";
    case "block": return "var(--amber)";
    default: return "var(--muted)";
  }
}

function levelLabel(level: string | null): string {
  switch (level) {
    case "open": return "OPENED";
    case "candidate": return "CANDIDATE";
    case "block": return "BLOCKED";
    default: return "INFO";
  }
}

function fmtTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleTimeString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function LogContent() {
  const [rows, setRows] = useState<ActivityLogEntry[]>([]);
  const [gates, setGates] = useState<GateStats | null>(null);
  const [gateWindow, setGateWindow] = useState<"24h" | "7d" | "30d">("24h");
  const [symbolFilter, setSymbolFilter] = useState<string>("all");
  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.activityLog(400), api.gateStats(gateWindow)])
      .then(([r, g]) => { setRows(r); setGates(g); setError(null); })
      .catch(() => setError("Cannot reach API — retrying"))
      .finally(() => setLoaded(true));
  }, [gateWindow]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const symbols = useMemo(() => {
    const set = new Set<string>();
    rows.forEach(r => { if (r.symbol) set.add(r.symbol); });
    return Array.from(set).sort();
  }, [rows]);

  const filtered = useMemo(() => rows.filter(r =>
    (symbolFilter === "all" || r.symbol === symbolFilter) &&
    (levelFilter === "all" || r.level === levelFilter)
  ), [rows, symbolFilter, levelFilter]);

  const selectStyle: React.CSSProperties = {
    background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 10px", fontSize: 13, minHeight: 40,
  };

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 1100, margin: "0 auto" }}>
        <div style={{ marginBottom: 16 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Live Log</h1>
          <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>
            Every decision the agent makes each candle — why it entered, or why it stood aside. Auto-refreshes.
          </p>
        </div>

        {error && (
          <div role="alert" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)", borderRadius: 10, padding: "10px 16px", fontSize: 12, marginBottom: 14 }}>
            {error}
          </div>
        )}

        {/* Why-idle summary strip */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 16, marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)" }}>
              Why the bot looks idle — top rejections
            </span>
            <div style={{ display: "flex", gap: 4 }}>
              {(["24h", "7d", "30d"] as const).map(w => (
                <button key={w} onClick={() => setGateWindow(w)}
                  style={{
                    background: gateWindow === w ? "var(--surface3)" : "transparent",
                    color: gateWindow === w ? "var(--text)" : "var(--muted)",
                    border: "1px solid var(--border)", borderRadius: 7, padding: "5px 10px",
                    fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}>
                  {w}
                </button>
              ))}
            </div>
          </div>
          {!gates || gates.total === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>
              {loaded ? `No gate rejections recorded in the last ${gateWindow}.` : "Loading…"}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {gates.gates.map(g => {
                const pct = gates.total ? (g.count / gates.total) * 100 : 0;
                return (
                  <div key={g.gate} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ width: 210, flexShrink: 0, fontSize: 12.5, color: "var(--text)" }}>{g.label}</span>
                    <div style={{ flex: 1, minWidth: 60, height: 8, background: "var(--surface2)", borderRadius: 4, overflow: "hidden" }}>
                      <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)", borderRadius: 4 }} />
                    </div>
                    <span style={{ width: 78, flexShrink: 0, textAlign: "right", fontSize: 12, fontVariantNumeric: "tabular-nums", color: "var(--muted)" }}>
                      {g.count} · {pct.toFixed(0)}%
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
          <select value={symbolFilter} onChange={e => setSymbolFilter(e.target.value)} style={selectStyle} aria-label="Filter by symbol">
            <option value="all">All symbols</option>
            {symbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={levelFilter} onChange={e => setLevelFilter(e.target.value)} style={selectStyle} aria-label="Filter by level">
            <option value="all">All levels</option>
            <option value="open">Opened</option>
            <option value="candidate">Candidate</option>
            <option value="block">Blocked</option>
            <option value="info">Info</option>
          </select>
          <span style={{ alignSelf: "center", fontSize: 12, color: "var(--muted)" }}>{filtered.length} shown</span>
        </div>

        {/* Feed */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
          {filtered.length === 0 ? (
            <div style={{ padding: 20, color: "var(--muted)", fontSize: 13 }}>
              {loaded ? "No activity matches the current filters yet. The agent writes a line for each coin at every candle close." : "Loading…"}
            </div>
          ) : (
            filtered.map(r => (
              <div key={r.id} style={{
                display: "grid", gridTemplateColumns: "auto 84px 1fr", gap: 12, alignItems: "baseline",
                padding: "9px 14px", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontSize: 11, color: "var(--muted)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{fmtTime(r.created_at)}</span>
                <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.04em", color: levelColor(r.level) }}>{levelLabel(r.level)}</span>
                <span style={{ fontSize: 13, color: "var(--text)", minWidth: 0, overflowWrap: "anywhere" }}>
                  {r.symbol && <span style={{ fontWeight: 700 }}>{r.symbol.replace("/USDT", "")}</span>}
                  {r.symbol && " — "}
                  <span style={{ color: r.level === "block" ? "var(--text)" : "var(--muted)" }}>{r.message}</span>
                </span>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <LogContent />
    </AuthGate>
  );
}
