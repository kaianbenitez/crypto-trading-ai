"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AgentStatus, api, Summary, Trade } from "@/lib/api";

// ── formatters ─────────────────────────────────────────────────────────────
const money  = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const price4 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const pct    = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

// ── coin logo ───────────────────────────────────────────────────────────────
function coinSlug(symbol: string) {
  return symbol.replace("/USDT", "").replace("/USD", "").toLowerCase();
}
function CoinLogo({ symbol, size = 28 }: { symbol: string; size?: number }) {
  const slug = coinSlug(symbol);
  const [err, setErr] = useState(false);
  if (err) {
    return (
      <span
        style={{ width: size, height: size, fontSize: size * 0.45, background: "var(--surface3)", border: "1px solid var(--border2)", borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontWeight: 600, flexShrink: 0 }}
      >
        {slug.slice(0, 2).toUpperCase()}
      </span>
    );
  }
  return (
    <img
      src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/32/color/${slug}.png`}
      alt={slug}
      width={size}
      height={size}
      onError={() => setErr(true)}
      style={{ borderRadius: "50%", flexShrink: 0, objectFit: "contain" }}
    />
  );
}

// ── helpers ─────────────────────────────────────────────────────────────────
function serviceText(v?: string) { return !v ? "—" : v === "active" ? "Online" : v === "inactive" ? "Offline" : v; }
function serviceColor(v?: string) {
  if (v === "active")   return "var(--green)";
  if (v === "inactive" || v === "failed") return "var(--red)";
  return "var(--muted)";
}
function pnlColor(v: number) { return v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text)"; }

const REGIME_META: Record<string, { label: string; color: string }> = {
  extreme_fear:  { label: "Extreme Fear",    color: "var(--red)"   },
  extreme_greed: { label: "Extreme Greed",   color: "var(--amber)" },
  crowded_long:  { label: "Crowded Longs",   color: "var(--amber)" },
  crowded_short: { label: "Crowded Shorts",  color: "var(--amber)" },
  risk_off:      { label: "Risk Off",        color: "var(--red)"   },
  normal:        { label: "Normal",          color: "var(--green)" },
};

// ── primitives ───────────────────────────────────────────────────────────────
function Badge({ children, color, bg }: { children: React.ReactNode; color?: string; bg?: string }) {
  const c = color || "var(--muted)";
  return (
    <span style={{ color: c, background: bg || c + "18", border: `1px solid ${c}30`, borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 600, letterSpacing: "0.03em", display: "inline-flex", alignItems: "center", gap: 4, whiteSpace: "nowrap" }}>
      {children}
    </span>
  );
}

function Dot({ state }: { state?: string }) {
  const color = serviceColor(state);
  const active = state === "active";
  return (
    <span
      className={active ? "pulse-dot" : ""}
      style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: color, flexShrink: 0 }}
      role="img"
      aria-label={serviceText(state)}
    />
  );
}

function Skeleton({ w, h }: { w?: string; h?: number }) {
  return <span className="skeleton" style={{ display: "block", width: w || "60%", height: h || 20 }} />;
}

// ── stat card ────────────────────────────────────────────────────────────────
function StatCard({
  label, value, sub, color, loading, accent, large
}: {
  label: string; value: string; sub?: string; color?: string; loading?: boolean; accent?: string; large?: boolean;
}) {
  return (
    <div style={{
      background: accent
        ? `linear-gradient(135deg, ${accent}14 0%, var(--surface) 70%)`
        : "var(--surface)",
      border: `1px solid ${accent ? accent + "25" : "var(--border)"}`,
      borderRadius: 14,
      padding: large ? "20px 20px" : "14px 16px",
      position: "relative",
      overflow: "hidden",
    }}>
      {accent && <span style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg, ${accent}, ${accent}00)`, borderRadius: "14px 14px 0 0" }} />}
      <div style={{ color: "var(--muted)", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</div>
      {loading ? (
        <Skeleton h={large ? 32 : 24} />
      ) : (
        <div style={{ color: color || "var(--text)", fontSize: large ? 26 : 20, fontWeight: 700, marginTop: 6, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>{value}</div>
      )}
      {sub && !loading && <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// ── PnlBar: visual range bar for entry/SL/TP ────────────────────────────────
function PnlBar({ trade }: { trade: Trade }) {
  const { entry_price, stop_loss, take_profit, side } = trade;
  const lo = Math.min(entry_price, stop_loss, take_profit);
  const hi = Math.max(entry_price, stop_loss, take_profit);
  const span = hi - lo || 1;
  const pos  = (v: number) => `${((v - lo) / span) * 100}%`;

  return (
    <div style={{ position: "relative", height: 6, background: "var(--surface3)", borderRadius: 3, margin: "12px 0 4px" }}>
      {/* SL zone */}
      {side === "long" ? (
        <div style={{ position: "absolute", left: pos(stop_loss), right: `${100 - parseFloat(pos(entry_price))}%`, height: "100%", background: "var(--red)", opacity: 0.35, borderRadius: 3 }} />
      ) : (
        <div style={{ position: "absolute", left: pos(entry_price), right: `${100 - parseFloat(pos(stop_loss))}%`, height: "100%", background: "var(--red)", opacity: 0.35, borderRadius: 3 }} />
      )}
      {/* TP zone */}
      {side === "long" ? (
        <div style={{ position: "absolute", left: pos(entry_price), right: `${100 - parseFloat(pos(take_profit))}%`, height: "100%", background: "var(--green)", opacity: 0.35, borderRadius: 3 }} />
      ) : (
        <div style={{ position: "absolute", left: pos(take_profit), right: `${100 - parseFloat(pos(entry_price))}%`, height: "100%", background: "var(--green)", opacity: 0.35, borderRadius: 3 }} />
      )}
      {/* Markers */}
      {[
        { price: stop_loss,   color: "var(--red)",   label: "SL" },
        { price: entry_price, color: "var(--accent)", label: "E"  },
        { price: take_profit, color: "var(--green)",  label: "TP" },
      ].map(({ price: p, color: c, label }) => (
        <div key={label} style={{ position: "absolute", left: pos(p), transform: "translateX(-50%)", top: -3, width: 12, height: 12, borderRadius: "50%", background: c, border: "2px solid var(--surface)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2 }} title={`${label}: ${price4.format(p)}`} />
      ))}
    </div>
  );
}

// ── open position card ───────────────────────────────────────────────────────
function OpenPosition({ trade }: { trade: Trade }) {
  const sideColor = trade.side === "long" ? "var(--green)" : "var(--red)";
  return (
    <div style={{ background: "var(--surface)", border: `1px solid ${sideColor}22`, borderRadius: 14, padding: "16px 20px", position: "relative", overflow: "hidden" }}>
      <span style={{ position: "absolute", top: 0, left: 0, bottom: 0, width: 3, background: sideColor, borderRadius: "14px 0 0 14px" }} />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <CoinLogo symbol={trade.symbol} size={30} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{trade.symbol.replace("/USDT", "")}<span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 12 }}>/USDT</span></div>
            <div style={{ color: "var(--muted)", fontSize: 11 }}>{trade.strategy_name} · {trade.regime}</div>
          </div>
          <Badge color={sideColor}>{trade.side.toUpperCase()}</Badge>
        </div>
        <Badge color="var(--amber)">OPEN</Badge>
      </div>

      {/* Range bar */}
      <PnlBar trade={trade} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)", marginBottom: 10 }}>
        <span>SL {price4.format(trade.stop_loss)}</span>
        <span style={{ color: "var(--accent)" }}>Entry {price4.format(trade.entry_price)}</span>
        <span>TP {price4.format(trade.take_profit)}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        {[
          { label: "Leverage", value: `${trade.leverage}×` },
          { label: "Qty", value: trade.qty ? price4.format(trade.qty) : "—" },
          { label: "Opened", value: new Date(trade.opened_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: "var(--surface2)", borderRadius: 8, padding: "8px 10px" }}>
            <div style={{ color: "var(--muted)", fontSize: 10, marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 13, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</div>
          </div>
        ))}
      </div>

      {trade.entry_reasoning[0] && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)", color: "var(--muted)", fontSize: 11, lineHeight: 1.5 }}>
          {trade.entry_reasoning[0]}
        </div>
      )}
    </div>
  );
}

// ── trade row ────────────────────────────────────────────────────────────────
function TradeRow({ trade }: { trade: Trade }) {
  const pnl = trade.pnl_usdt ?? 0;
  const sideColor = trade.side === "long" ? "var(--green)" : "var(--red)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--border)" }} className="last:border-b-0">
      <CoinLogo symbol={trade.symbol} size={22} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{trade.symbol.replace("/USDT", "")}</span>
          <Badge color={sideColor}>{trade.side.toUpperCase()}</Badge>
          {trade.outcome && <Badge>{trade.outcome}</Badge>}
        </div>
        <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {trade.exit_reason || trade.entry_reasoning[0] || "—"}
        </div>
      </div>
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ color: pnlColor(pnl), fontWeight: 700, fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
          {pnl >= 0 ? "+" : ""}{money.format(pnl)} <span style={{ fontSize: 10, fontWeight: 400 }}>USDT</span>
        </div>
        <div style={{ color: "var(--muted)", fontSize: 10, marginTop: 2 }}>
          {trade.closed_at ? new Date(trade.closed_at).toLocaleDateString([], { month: "short", day: "numeric" }) : "—"}
        </div>
      </div>
    </div>
  );
}

// ── card shell ───────────────────────────────────────────────────────────────
function Card({ title, right, children, noPad }: { title: string; right?: React.ReactNode; children: React.ReactNode; noPad?: boolean }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 20px", borderBottom: "1px solid var(--border)" }}>
        <span style={{ fontWeight: 600, fontSize: 12, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>{title}</span>
        {right}
      </div>
      <div style={noPad ? {} : { padding: "0 20px" }}>{children}</div>
    </div>
  );
}

// ── nav bar ──────────────────────────────────────────────────────────────────
function NavBar({ killActive, status }: { killActive?: boolean; status?: AgentStatus | null }) {
  const agentOk = status?.trading_agent === "active";
  return (
    <nav style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)", padding: "0 24px", height: 52, display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 50, backdropFilter: "blur(8px)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 20, height: 20, background: "linear-gradient(135deg, var(--accent), var(--accent2))", borderRadius: 5, display: "inline-block", flexShrink: 0 }} />
          <span style={{ fontWeight: 700, fontSize: 14, letterSpacing: "-0.01em" }}>TradingAI</span>
        </div>
        {[
          { label: "Dashboard", href: "/" },
          { label: "Journal",   href: "/journal" },
          { label: "Signals",   href: "/signals" },
        ].map(({ label, href }) => (
          <a key={href} href={href} style={{ color: "var(--muted)", fontSize: 13, textDecoration: "none", transition: "color 0.15s" }}
             onMouseEnter={e => (e.currentTarget.style.color = "var(--text)")}
             onMouseLeave={e => (e.currentTarget.style.color = "var(--muted)")}
          >{label}</a>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {/* Agent health pill */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--surface2)", border: `1px solid ${agentOk ? "var(--green)22" : "var(--border)"}`, borderRadius: 20, padding: "4px 10px" }}>
          <Dot state={status?.trading_agent} />
          <span style={{ fontSize: 11, fontWeight: 600, color: agentOk ? "var(--green)" : "var(--muted)" }}>
            {agentOk ? "Agent live" : "Agent offline"}
          </span>
        </div>
        {/* Testnet badge */}
        {status?.testnet && (
          <Badge color="var(--amber)">TESTNET</Badge>
        )}
        {/* Kill switch status */}
        {killActive && (
          <Badge color="var(--red)">HALTED</Badge>
        )}
      </div>
    </nav>
  );
}

// ── kill switch button ───────────────────────────────────────────────────────
function KillSwitchButton({ killActive, toggling, confirming, onHalt, onConfirm, onCancel, onResume, cancelRef }: {
  killActive?: boolean; toggling: boolean; confirming: boolean;
  onHalt: () => void; onConfirm: () => void; onCancel: () => void; onResume: () => void;
  cancelRef: React.RefObject<HTMLButtonElement | null>;
}) {
  if (confirming) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ color: "var(--muted)", fontSize: 12 }}>Confirm halt?</span>
      <button onClick={onConfirm} disabled={toggling} aria-label="Confirm halt"
        style={{ background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.5)", color: "var(--red)", borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
        Yes, halt
      </button>
      <button ref={cancelRef} onClick={onCancel} aria-label="Cancel"
        style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)", borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
        Cancel
      </button>
    </div>
  );

  if (killActive) return (
    <button onClick={onResume} disabled={toggling} aria-label="Resume trading"
      style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "var(--red)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 10 }}>▶</span> {toggling ? "Resuming…" : "Resume trading"}
    </button>
  );

  return (
    <button onClick={onHalt} disabled={toggling} aria-label="Halt new entries"
      style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--red)", display: "inline-block" }} />
      {toggling ? "Halting…" : "Halt entries"}
    </button>
  );
}

// ── main dashboard ───────────────────────────────────────────────────────────
function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [status,  setStatus]  = useState<AgentStatus | null>(null);
  const [trades,  setTrades]  = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling,      setToggling]      = useState(false);
  const [confirmingHalt,setConfirmingHalt]= useState(false);
  const [error,         setError]         = useState<string | null>(null);
  const [toggleError,   setToggleError]   = useState<string | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  async function load() {
    try {
      const [s, st, t] = await Promise.all([api.summary(), api.agentStatus(), api.trades(15)]);
      setSummary(s); setStatus(st); setTrades(t); setError(null);
    } catch {
      setError("Cannot reach API — retrying every 15 s");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!confirmingHalt) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setConfirmingHalt(false); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmingHalt]);

  async function confirmHalt() {
    setConfirmingHalt(false); setToggling(true); setToggleError(null);
    try { await api.setKillSwitch(true, "manual halt"); await load(); }
    catch { setToggleError("Halt failed — check server logs."); }
    finally { setToggling(false); }
  }

  async function resumeTrading() {
    setToggling(true); setToggleError(null);
    try { await api.setKillSwitch(false, "manual resume"); await load(); }
    catch { setToggleError("Resume failed — check server logs."); }
    finally { setToggling(false); }
  }

  const lastChecked = useMemo(() => {
    if (!status?.checked_at) return "—";
    const d = new Date(status.checked_at);
    return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " +
           d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }, [status?.checked_at]);

  const openTrades   = trades.filter(t => !t.closed_at);
  const closedTrades = trades.filter(t =>  t.closed_at);
  const killActive   = summary?.kill_switch_active;
  const regime       = status?.macro_regime || "normal";
  const regimeMeta   = REGIME_META[regime] || { label: regime, color: "var(--muted)" };
  const totalPnl     = closedTrades.reduce((sum, t) => sum + (t.pnl_usdt ?? 0), 0);

  return (
    <div style={{ minHeight: "100dvh", background: "var(--bg)" }}>
      <NavBar killActive={killActive} status={status} />

      {/* HALTED banner */}
      {killActive && (
        <div role="status" aria-live="polite"
          style={{ background: "rgba(239,68,68,0.08)", borderBottom: "1px solid rgba(239,68,68,0.25)", color: "var(--red)", padding: "9px 24px", fontSize: 12, fontWeight: 600, textAlign: "center", letterSpacing: "0.05em" }}>
          ▐▐ TRADING HALTED — all new entries blocked
        </div>
      )}

      <main style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 20px 60px" }}>

        {/* Header row */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Dashboard</h1>
            <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>
              {loading ? "Connecting…" : `Updated ${lastChecked}`}
            </p>
          </div>
          <KillSwitchButton
            killActive={killActive}
            toggling={toggling}
            confirming={confirmingHalt}
            onHalt={() => { setConfirmingHalt(true); setTimeout(() => cancelRef.current?.focus(), 0); }}
            onConfirm={confirmHalt}
            onCancel={() => setConfirmingHalt(false)}
            onResume={resumeTrading}
            cancelRef={cancelRef}
          />
        </div>

        {/* Errors */}
        {error && (
          <div role="alert" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)", borderRadius: 10, padding: "10px 16px", fontSize: 12, marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <span>{error}</span>
            <button onClick={load} style={{ background: "none", border: "none", color: "var(--red)", textDecoration: "underline", cursor: "pointer", fontSize: 12, flexShrink: 0 }}>Retry</button>
          </div>
        )}
        {toggleError && (
          <div role="alert" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)", borderRadius: 10, padding: "10px 16px", fontSize: 12, marginBottom: 16 }}>
            {toggleError}
          </div>
        )}

        {/* Stat row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10, marginBottom: 18 }}>
          <StatCard label="Bankroll" value={summary ? `$${money.format(summary.bankroll_usdt)}` : "—"} sub="USDT balance" loading={loading} accent="var(--accent)" />
          <StatCard label="ROI" value={summary ? pct(summary.roi_pct) : "—"} color={summary ? pnlColor(summary.roi_pct) : undefined} sub="all-time" loading={loading} accent={summary ? pnlColor(summary.roi_pct) : undefined} />
          <StatCard label="Realized P&L" value={closedTrades.length ? `${totalPnl >= 0 ? "+" : ""}$${money.format(totalPnl)}` : "—"} color={pnlColor(totalPnl)} sub={`${closedTrades.length} closed trades`} loading={loading} accent={pnlColor(totalPnl)} />
          <StatCard label="Win Rate" value={summary ? `${summary.win_rate_pct.toFixed(1)}%` : "—"} sub={summary ? `${summary.total_trades} total` : undefined} loading={loading} />
          <StatCard label="Open" value={summary ? String(summary.open_positions) : "—"} color={summary && summary.open_positions > 0 ? "var(--amber)" : undefined} sub="positions" loading={loading} accent={summary && summary.open_positions > 0 ? "var(--amber)" : undefined} />
          <StatCard label="Macro" value={regimeMeta.label} color={regimeMeta.color} sub={`size ×${status ? (status as AgentStatus & { size_multiplier?: number }).size_multiplier?.toFixed(2) ?? "—" : "—"}`} loading={loading} accent={regimeMeta.color} />
        </div>

        {/* Middle row: services + symbols | open positions */}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 320px) 1fr", gap: 12, marginBottom: 18 }}>

          {/* Left col: services + market */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Card title="Services">
              <div>
                {[
                  { name: "Trading Agent", key: "trading_agent" as keyof AgentStatus },
                  { name: "API Backend",   key: "webapi"         as keyof AgentStatus },
                  { name: "Dashboard",     key: "dashboard"      as keyof AgentStatus },
                  { name: "Nginx",         key: "nginx"          as keyof AgentStatus },
                  { name: "Exchange",      key: "exchange"       as keyof AgentStatus },
                ].map(({ name, key }) => {
                  const state = status?.[key] as string | undefined;
                  return (
                    <div key={name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderBottom: "1px solid var(--border)" }} className="last:border-b-0">
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Dot state={state} />
                        <span style={{ color: "var(--muted)", fontSize: 12 }}>{name}</span>
                      </div>
                      {loading ? <Skeleton w="50px" h={14} /> : (
                        <span style={{ color: serviceColor(state), fontSize: 12, fontWeight: 600 }}>{serviceText(state)}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card title="Market" right={<Badge color={regimeMeta.color}>{regimeMeta.label}</Badge>}>
              <div style={{ padding: "12px 0" }}>
                <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 8, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Active symbols</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {(status?.symbols?.length ? status.symbols : [
                    "BTC/USDT","ETH/USDT","XRP/USDT","SOL/USDT","ADA/USDT",
                    "BNB/USDT","DOGE/USDT","AVAX/USDT","LINK/USDT","DOT/USDT",
                    "POL/USDT","LTC/USDT","UNI/USDT","ATOM/USDT","FIL/USDT",
                  ]).map(s => (
                    <div key={s} style={{ display: "flex", alignItems: "center", gap: 5, background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "4px 8px" }}>
                      <CoinLogo symbol={s} size={16} />
                      <span style={{ fontSize: 12, fontWeight: 600 }}>{s.replace("/USDT", "")}</span>
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
                  <span style={{ color: "var(--muted)", fontSize: 12 }}>Kill switch</span>
                  <Badge color={killActive ? "var(--red)" : "var(--green)"}>{killActive ? "ON" : "OFF"}</Badge>
                </div>
              </div>
            </Card>
          </div>

          {/* Right col: open positions */}
          <div>
            <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
              <h2 style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", margin: 0 }}>Open Positions</h2>
              {openTrades.length > 0 && <Badge color="var(--amber)">{openTrades.length}</Badge>}
            </div>
            {openTrades.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {openTrades.map(t => <OpenPosition key={t.id} trade={t} />)}
              </div>
            ) : (
              <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: "48px 24px", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
                {loading ? "Loading positions…" : "No active positions — scanning for setups"}
              </div>
            )}
          </div>
        </div>

        {/* Recent closed trades */}
        <Card title="Recent Closed Trades" right={<a href="/journal" style={{ color: "var(--accent)", fontSize: 11, textDecoration: "none" }}>View all →</a>}>
          {loading ? (
            <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>Loading…</div>
          ) : closedTrades.length > 0 ? (
            closedTrades.map(t => <TradeRow key={t.id} trade={t} />)
          ) : (
            <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>No closed trades yet</div>
          )}
        </Card>

      </main>
    </div>
  );
}

export default function Page() {
  return <Dashboard />;
}
