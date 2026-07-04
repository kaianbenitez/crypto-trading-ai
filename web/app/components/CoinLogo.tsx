"use client";

import { useState } from "react";

function coinSlug(symbol: string) {
  const base = symbol.replace("/USDT", "").replace("/USD", "").toLowerCase();
  return base === "pol" ? "matic" : base;
}

export default function CoinLogo({ symbol, size = 28 }: { symbol: string; size?: number }) {
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
