"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, Broadcast, ChartLineUp, ClockCounterClockwise, Eye, Gauge, GearSix, Lightbulb, ShieldWarning, Sparkle } from "@phosphor-icons/react";

const items = [
  ["Dashboard", "/", Gauge],
  ["Live Log", "/log", Broadcast],
  ["Journal", "/journal", BookOpen],
  ["Coin Watch", "/coins", Eye],
  ["Risk", "/risk", ShieldWarning],
  ["Strategy", "/strategy", ChartLineUp],
  ["Insights", "/insights", Lightbulb],
  ["Adaptive", "/adaptive", Sparkle],
  ["Changelog", "/changelog", ClockCounterClockwise],
  ["Settings", "/settings", GearSix],
] as const;

export default function AppNav() {
  const pathname = usePathname();
  return (
    <aside className="global-nav">
      <Link href="/" className="global-nav__brand">Trading<span>AI</span></Link>
      <nav className="global-nav__links" aria-label="Main navigation">
        {items.map(([label, href, Icon]) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href} className={`global-nav__link${active ? " is-active" : ""}`}>
              <Icon size={18} weight={active ? "fill" : "regular"} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="global-nav__footer"><span className="global-nav__dot" />Connected</div>
    </aside>
  );
}
