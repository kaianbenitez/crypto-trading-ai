"use client";

import { useEffect, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import CoinLogo from "../components/CoinLogo";
import { api, NewsStatus, RosterInfo, Summary } from "@/lib/api";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontWeight: 600, fontSize: 12, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)" }}>{title}</div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  );
}

function SettingsContent() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [roster, setRoster] = useState<RosterInfo | null>(null);
  const [news, setNews] = useState<NewsStatus | null>(null);
  const [toggling, setToggling] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    Promise.all([api.summary(), api.roster(), api.newsStatus()])
      .then(([s, r, n]) => { setSummary(s); setRoster(r); setNews(n); })
      .catch(() => setError("Could not load settings"));
  }

  useEffect(() => { load(); }, []);

  async function toggleKillSwitch(active: boolean) {
    setToggling(true);
    try {
      await api.setKillSwitch(active, active ? "manual halt (settings page)" : "manual resume (settings page)");
      load();
    } catch {
      setError("Failed to update kill switch");
    } finally {
      setToggling(false);
      setConfirming(false);
    }
  }

  const killActive = summary?.kill_switch_active;

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 900, margin: "0 auto" }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Settings</h1>
          <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>Trading controls and which coins are currently in rotation.</p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Trading">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>
                  {killActive ? "🔴 New entries are halted" : "🟢 Trading normally"}
                </div>
                <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 2 }}>
                  {killActive
                    ? "The agent will keep managing any open positions but won't open new trades."
                    : "The agent can open new trades whenever it finds a good setup."}
                </div>
              </div>
              {confirming ? (
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => toggleKillSwitch(true)} disabled={toggling}
                    style={{ background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.5)", color: "var(--red)", borderRadius: 8, padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
                    Yes, halt entries
                  </button>
                  <button onClick={() => setConfirming(false)} disabled={toggling}
                    style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)", borderRadius: 8, padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
                    Cancel
                  </button>
                </div>
              ) : killActive ? (
                <button onClick={() => toggleKillSwitch(false)} disabled={toggling}
                  style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.4)", color: "var(--green)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                  {toggling ? "Resuming…" : "Resume trading"}
                </button>
              ) : (
                <button onClick={() => setConfirming(true)} disabled={toggling}
                  style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                  Halt new entries
                </button>
              )}
            </div>
          </Card>

          <Card title="Market scanner">
            {roster?.scan ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: "50%",
                    background: !roster.scan.enabled ? "var(--muted)" : roster.scan.status === "ok" ? "var(--green)" : roster.scan.status === "error" ? "var(--red)" : "var(--amber)",
                  }} />
                  <span style={{ fontSize: 13, fontWeight: 600 }}>
                    {!roster.scan.enabled ? "Disabled — using fixed 15-coin list" : roster.scan.status === "ok" ? "Scanning the market" : roster.scan.status === "error" ? "Scan failed — using fallback" : "Not run yet"}
                  </span>
                </div>
                {roster.scan.enabled && (
                  <div style={{ color: "var(--muted)", fontSize: 12, lineHeight: 1.6 }}>
                    {roster.scan.last_scan_at && (
                      <div>Last scan: {new Date(roster.scan.last_scan_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</div>
                    )}
                    {roster.scan.scanned !== undefined && (
                      <div>{roster.scan.scanned} pairs scanned → {roster.scan.eligible} eligible → {roster.scan.selected_count} shortlisted</div>
                    )}
                    {roster.scan.error && <div style={{ color: "var(--red)" }}>Error: {roster.scan.error}</div>}
                  </div>
                )}
              </>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</div>
            )}
          </Card>

          <Card title="News context">
            {news ? (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: news.enabled ? "var(--green)" : "var(--muted)" }} />
                <span style={{ fontSize: 13, fontWeight: 600 }}>{news.enabled ? `Enabled (${news.provider})` : "Disabled"}</span>
              </div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</div>
            )}
            <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 8 }}>
              Context only — headlines never open a trade directly, at most a small confidence nudge on an already-qualified setup.
            </div>
          </Card>

          <Card title="Active coin roster">
            {roster && roster.active.length > 0 ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {roster.active.map(sym => (
                  <div key={sym} style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px" }}>
                    <CoinLogo symbol={sym} size={16} />
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{sym.replace("/USDT", "")}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 13 }}>No active symbols loaded yet.</div>
            )}
            <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 10 }}>
              The agent automatically benches and reinstates coins during its daily review (low volume, losing streaks) — there's no manual override here yet.
            </div>
          </Card>

          {roster && roster.benched.length > 0 && (
            <Card title="Benched coins">
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {roster.benched.map(b => (
                  <div key={b.symbol} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <CoinLogo symbol={b.symbol} size={16} />
                      <span style={{ fontSize: 12, fontWeight: 600 }}>{b.symbol.replace("/USDT", "")}</span>
                    </div>
                    <span style={{ color: "var(--muted)", fontSize: 11 }}>
                      back in rotation {new Date(b.until).toLocaleDateString([], { month: "short", day: "numeric" })}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <SettingsContent />
    </AuthGate>
  );
}
