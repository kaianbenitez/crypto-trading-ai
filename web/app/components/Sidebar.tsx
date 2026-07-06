"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
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
  { label: "Dashboard",  href: "/" },
  { label: "Journal",    href: "/journal" },
  { label: "Coin Watch", href: "/coins" },
  { label: "Risk",       href: "/risk" },
  { label: "Adaptive",   href: "/adaptive" },
  { label: "Settings",   href: "/settings" },
  { label: "Changelog",  href: "/changelog" },
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
          <span style={{ width: 22, height: 22, background: "linear-gradient(135deg, var(--accent), var(--accent2))", borderRadius: 6, display: "inline-block", flexShrink: 0 }} />
          <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text)" }}>TradingAI</span>
        </Link>

        <button
          className="sidebar-hamburger"
          onClick={() => setNavOpen(o => !o)}
          aria-label={navOpen ? "Close menu" : "Open menu"}
          aria-expanded={navOpen}
        >
          <span style={{ position: "relative", width: 18, height: 13 }}>
            {[0, 1, 2].map(i => (
              <span key={i} style={{
                position: "absolute", left: 0, right: 0, height: 2, background: "var(--text)", borderRadius: 1,
                top: i === 0 ? 0 : i === 1 ? 5.5 : 11,
                transform: navOpen && i === 1 ? "scaleX(0)" : navOpen && i === 0 ? "translateY(5.5px) rotate(45deg)" : navOpen && i === 2 ? "translateY(-5.5px) rotate(-45deg)" : undefined,
                transition: "transform 180ms ease, opacity 180ms ease",
              }} />
            ))}
          </span>
        </button>
      </div>

      <div className="sidebar-backdrop" data-open={navOpen} onClick={() => setNavOpen(false)} />

      <div className="sidebar-body" data-open={navOpen}>
        <nav style={{ flex: 1, padding: "4px 10px" }}>
          {NAV_ITEMS.map(item => {
            const active = pathname === item.href;
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
                {item.label}
              </Link>
            );
          })}

          <div style={{ margin: "10px 0 6px", borderTop: "1px solid var(--border)" }} />
          <span style={{ fontSize: 10, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.08em", padding: "0 10px", display: "block", marginBottom: 4 }}>SPORTS</span>
          <a
            href={MLB_URL}
            target="_blank"
            rel="noreferrer"
            className="nav-link"
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              color: "var(--muted)", fontWeight: 500,
            }}
          >
            <span>MLB Bets</span>
            <span style={{ fontSize: 10, opacity: 0.5 }}>↗</span>
          </a>
        </nav>

        <div ref={ref} style={{ padding: 10, borderTop: "1px solid var(--border)", position: "relative" }}>
          {open && (
            <div style={{ position: "absolute", bottom: "calc(100% + 6px)", left: 10, right: 10, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 6, zIndex: 100, boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }}>
              {SERVICE_LIST.map((s, i) => (
                <div key={s.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 6px", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Dot state={states[i]} />
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>{s.name}</span>
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 600, color: serviceColor(states[i]) }}>{serviceText(states[i])}</span>
                </div>
              ))}
              {status?.exchange && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 6px", gap: 12, marginTop: 2, borderTop: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>Exchange</span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)" }}>{status.exchange}{status.testnet ? " (testnet)" : ""}</span>
                </div>
              )}
            </div>
          )}

          {status?.testnet && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: "var(--amber)", background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.3)", borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 600 }}>TESTNET</span>
            </div>
          )}

          <button onClick={() => setOpen(o => !o)} aria-label="Service status" style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: 0, cursor: "pointer", padding: "6px 0", width: "100%", minHeight: 32 }}>
            <span className={allOk ? "pulse-dot" : ""} style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, flexShrink: 0 }} />
            <span style={{ fontSize: 12, fontWeight: 600, color: dotColor }}>{label}</span>
          </button>

          <button onClick={handleLogout} style={{ marginTop: 6, background: "transparent", border: 0, color: "var(--muted)", cursor: "pointer", fontSize: 12, padding: "6px 0" }}>
            Logout
          </button>
        </div>
      </div>
    </aside>
  );
}
