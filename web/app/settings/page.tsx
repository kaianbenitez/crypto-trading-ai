"use client";

import { useEffect, useState } from "react";
import { Circle, Newspaper } from "@phosphor-icons/react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import CoinLogo from "../components/CoinLogo";
import { api, NewsStatus, RosterInfo, StrategyProfile, Summary } from "@/lib/api";
import { Card, Button, Badge } from "../components/ui";

function StatusDot({ color }: { color: string }) {
  return <Circle size={8} weight="fill" color={color} />;
}

function SettingsContent() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [roster, setRoster] = useState<RosterInfo | null>(null);
  const [news, setNews] = useState<NewsStatus | null>(null);
  const [profile, setProfile] = useState<StrategyProfile | null>(null);
  const [toggling, setToggling] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    Promise.all([api.summary(), api.roster(), api.newsStatus(), api.strategyProfile()])
      .then(([s, r, n, p]) => { setSummary(s); setRoster(r); setNews(n); setProfile(p); })
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
          <h1 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0 }}>Settings</h1>
          <p style={{ color: "var(--muted)", fontSize: "var(--text-xs)", margin: "4px 0 0" }}>Trading controls and which coins are currently in rotation.</p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: "var(--text-sm)", marginBottom: 12 }}>{error}</div>}

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Trading">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusDot color={killActive ? "var(--red)" : "var(--green)"} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>
                    {killActive ? "New entries are halted" : "Trading normally"}
                  </div>
                  <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)", marginTop: 2 }}>
                    {killActive
                      ? "The agent will keep managing any open positions but won't open new trades."
                      : "The agent can open new trades whenever it finds a good setup."}
                  </div>
                </div>
              </div>
              {confirming ? (
                <div style={{ display: "flex", gap: 8 }}>
                  <Button variant="danger" onClick={() => toggleKillSwitch(true)} disabled={toggling}>Yes, halt entries</Button>
                  <Button variant="secondary" onClick={() => setConfirming(false)} disabled={toggling}>Cancel</Button>
                </div>
              ) : killActive ? (
                <Button variant="danger" onClick={() => toggleKillSwitch(false)} disabled={toggling}>
                  {toggling ? "Resuming…" : "Resume trading"}
                </Button>
              ) : (
                <Button variant="secondary" onClick={() => setConfirming(true)} disabled={toggling}>
                  Halt new entries
                </Button>
              )}
            </div>
          </Card>

          <Card title="Strategy profile">
            {profile ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                  <span style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{profile.profile}</span>
                  {profile.profile === "baseline_simple" && <Badge color="var(--accent)">clean baseline</Badge>}
                  {profile.profile === "full_agentic" && <Badge color="var(--amber)">full stack</Badge>}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                  <div>
                    <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Decides trades</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {profile.decision_active.map(m => (
                        <span key={m} className="ui-badge" style={{ color: "var(--green)", background: "color-mix(in oklab, var(--green) 14%, transparent)", borderColor: "color-mix(in oklab, var(--green) 30%, transparent)" }}>{m}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Observes only</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {profile.observe_only.length > 0 ? profile.observe_only.map(m => (
                        <span key={m} className="ui-badge" style={{ color: "var(--muted)", background: "var(--surface2)", borderColor: "var(--border)" }}>{m}</span>
                      )) : <span style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>none — every module is decision-active</span>}
                    </div>
                  </div>
                </div>
                <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 12 }}>
                  Observe-only modules still log their read for later comparison, but cannot change confidence, EV, sizing, or block/approve a trade. Change via the STRATEGY_PROFILE env var, then restart the agent.
                </div>
              </>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>Loading…</div>
            )}
          </Card>

          <Card title="Market scanner">
            {roster?.scan ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <StatusDot color={!roster.scan.enabled ? "var(--muted)" : roster.scan.status === "ok" ? "var(--green)" : roster.scan.status === "error" ? "var(--red)" : "var(--amber)"} />
                  <span style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
                    {!roster.scan.enabled ? "Disabled — using fixed 15-coin list" : roster.scan.status === "ok" ? "Scanning the market" : roster.scan.status === "error" ? "Scan failed — using fallback" : "Not run yet"}
                  </span>
                </div>
                {roster.scan.enabled && (
                  <div style={{ color: "var(--muted)", fontSize: "var(--text-xs)", lineHeight: 1.6 }}>
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
              <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>Loading…</div>
            )}
          </Card>

          <Card title="News context">
            {news ? (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Newspaper size={15} color={news.enabled ? "var(--green)" : "var(--muted)"} />
                <span style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>{news.enabled ? `Enabled (${news.provider})` : "Disabled"}</span>
              </div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>Loading…</div>
            )}
            <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 8 }}>
              Context only — headlines never open a trade directly, at most a small confidence nudge on an already-qualified setup.
            </div>
          </Card>

          <Card title="Active coin roster">
            {roster && roster.active.length > 0 ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {roster.active.map(sym => (
                  <div key={sym} style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "6px 10px" }}>
                    <CoinLogo symbol={sym} size={16} />
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 600 }}>{sym.replace("/USDT", "")}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>No active symbols loaded yet.</div>
            )}
            <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 10 }}>
              The agent automatically benches and reinstates coins during its daily review (low volume, losing streaks) — there&apos;s no manual override here yet.
            </div>
          </Card>

          {roster && roster.benched.length > 0 && (
            <Card title="Benched coins">
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {roster.benched.map(b => (
                  <div key={b.symbol} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "8px 10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <CoinLogo symbol={b.symbol} size={16} />
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 600 }}>{b.symbol.replace("/USDT", "")}</span>
                    </div>
                    <span style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>
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
