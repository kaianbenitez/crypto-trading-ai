"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Gauge, Broadcast, BookOpen, Eye, ShieldWarning, Brain, GearSix,
  ClockCounterClockwise, ArrowSquareOut, SignOut, List, X,
} from "@phosphor-icons/react";
import { AgentStatus, api } from "@/lib/api";

function serviceText(v?: string) { return !v ? "—" : v === "active" ? "Online" : v === "inactive" ? "Offline" : v; }
function serviceColor(v?: string) {
  if (v === "active") return "var(--green)";
  if (v === "inactive" || v === "failed") return "var(--red)";
  return "var(--muted)";
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

// Services whose value is a systemctl state — used for the overall health dot.
const SERVICE_LIST: { name: string; key: keyof AgentStatus }[] = [
  { name: "Trading Agent", key: "trading_agent" },
  { name: "API Backend",   key: "webapi" },
  { name: "Dashboard",     key: "dashboard" },
  { name: "Nginx",         key: "nginx" },
];

const NAV_ITEMS = [
  { label: "Dashboard",  href: "/",         icon: Gauge },
  { label: "Live Log",   href: "/log",      icon: Broadcast },
  { label: "Journal",    href: "/journal",  icon: BookOpen },
  { label: "Coin Watch", href: "/coins",    icon: Eye },
  { label: "Risk",       href: "/risk",     icon: ShieldWarning },
  { label: "Adaptive",   href: "/adaptive", icon: Brain },
  { label: "Settings",   href: "/settings", icon: GearSix },
  { label: "Changelog",  href: "/changelog", icon: ClockCounterClockwise },
];

const MLB_URL = "/mlb/";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [prevPathname, setPrevPathname] = useState(pathname);
  const ref = useRef<HTMLDivElement>(null);

  // Close the mobile drawer whenever the route changes (link tap navigates).
  // Adjusted during render (React's recommended pattern for derived state)
  // rather than in an effect, to avoid an extra post-navigation render.
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setNavOpen(false);
  }

  useEffect(() => {
    let cancelled = false;
    function load() {
      api.agentStatus().then(s => { if (!cancelled) setStatus(s); }).catch(() => {});
    }
    load();
    const id = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Escape closes the mobile drawer; lock body scroll while it's open.
  useEffect(() => {
    if (!navOpen) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setNavOpen(false); }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [navOpen]);

  async function handleLogout() {
    await api.logout().catch(() => {});
    router.push("/login");
  }

  const states = SERVICE_LIST.map(s => status?.[s.key] as string | undefined);
  const known = states.filter(Boolean);
  const allOk = known.length === SERVICE_LIST.length && known.every(s => s === "active");
  const anyDown = states.some(s => s === "inactive" || s === "failed");
  const dotColor = !status ? "var(--muted)" : anyDown ? "var(--amber)" : allOk ? "var(--green)" : "var(--muted)";
  const label = !status ? "Checking…" : anyDown ? "Needs attention" : allOk ? "Agent live" : "Checking…";

  return (
    <aside className="sidebar">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
        <Link href="/" style={{ padding: "18px 18px 14px", display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
          <span style={{ width: 24, height: 24, background: "var(--gradient-primary)", borderRadius: 7, display: "inline-block", flexShrink: 0, boxShadow: "0 2px 8px color-mix(in oklab, var(--accent) 45%, transparent)" }} />
          <span style={{ fontWeight: 700, fontSize: "var(--text-base)", color: "var(--text)" }}>TradingAI</span>
        </Link>

        <button
          className="sidebar-hamburger"
          onClick={() => setNavOpen(o => !o)}
          aria-label={navOpen ? "Close menu" : "Open menu"}
          aria-expanded={navOpen}
        >
          {navOpen ? <X size={20} weight="bold" /> : <List size={20} weight="bold" />}
        </button>
      </div>

      <div className="sidebar-backdrop" data-open={navOpen} onClick={() => setNavOpen(false)} />

      <div className="sidebar-body" data-open={navOpen}>
        <nav style={{ flex: 1, padding: "4px 10px" }}>
          {NAV_ITEMS.map(item => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="nav-link"
                style={{
                  color: active ? "var(--text)" : "var(--muted)",
                  background: active ? "var(--surface2)" : "transparent",
                  fontWeight: active ? 600 : 500,
                }}
              >
                <Icon size={16} weight={active ? "fill" : "regular"} style={{ flexShrink: 0, color: active ? "var(--accent)" : "currentColor" }} />
                {item.label}
              </Link>
            );
          })}

          <div style={{ margin: "10px 0 6px", borderTop: "1px solid var(--border)" }} />
          <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: "var(--muted)", letterSpacing: "0.08em", padding: "0 10px", display: "block", marginBottom: 4 }}>SPORTS</span>
          <a
            href={MLB_URL}
            target="_blank"
            rel="noreferrer"
            className="nav-link"
            style={{
              justifyContent: "space-between",
              color: "var(--muted)", fontWeight: 500,
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 10 }}>MLB Bets</span>
            <ArrowSquareOut size={13} style={{ opacity: 0.6 }} />
          </a>
        </nav>

        <div ref={ref} style={{ padding: 10, borderTop: "1px solid var(--border)", position: "relative" }}>
          {open && (
            <div className="rise-in" style={{ position: "absolute", bottom: "calc(100% + 6px)", left: 10, right: 10, background: "var(--surface2)", border: "1px solid var(--border2)", borderRadius: "var(--radius-sm)", padding: 6, zIndex: 100, boxShadow: "var(--shadow-lg)" }}>
              {SERVICE_LIST.map((s, i) => (
                <div key={s.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 6px", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Dot state={states[i]} />
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--muted)" }}>{s.name}</span>
                  </div>
                  <span style={{ fontSize: "var(--text-2xs)", fontWeight: 600, color: serviceColor(states[i]) }}>{serviceText(states[i])}</span>
                </div>
              ))}
              {status?.exchange && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 6px", gap: 12, marginTop: 2, borderTop: "1px solid var(--border)" }}>
                  <span style={{ fontSize: "var(--text-xs)", color: "var(--muted)" }}>Exchange</span>
                  <span style={{ fontSize: "var(--text-2xs)", fontWeight: 600, color: "var(--text)" }}>{status.exchange}{status.testnet ? " (testnet)" : ""}</span>
                </div>
              )}
            </div>
          )}

          {status?.testnet && (
            <div style={{ marginBottom: 8 }}>
              <span className="ui-badge" style={{ color: "var(--amber)", background: "color-mix(in oklab, var(--amber) 14%, transparent)", borderColor: "color-mix(in oklab, var(--amber) 32%, transparent)" }}>TESTNET</span>
            </div>
          )}

          <button onClick={() => setOpen(o => !o)} aria-label="Service status" style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: 0, cursor: "pointer", padding: "6px 0", width: "100%", minHeight: 32, borderRadius: "var(--radius-sm)", transition: "color var(--dur-base) var(--ease-out-quart)" }}>
            <span className={allOk ? "pulse-dot" : ""} style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, flexShrink: 0 }} />
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: dotColor }}>{label}</span>
          </button>

          <button onClick={handleLogout} className="ui-btn ui-btn--ghost" style={{ marginTop: 6, fontSize: "var(--text-xs)", justifyContent: "flex-start", gap: 6 }}>
            <SignOut size={13} /> Logout
          </button>
        </div>
      </div>
    </aside>
  );
}
