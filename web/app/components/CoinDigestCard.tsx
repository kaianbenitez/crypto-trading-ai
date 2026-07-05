import { CoinDigest } from "@/lib/api";
import { pct, pnlColor, price4 } from "@/lib/format";
import CoinLogo from "./CoinLogo";

const SENTIMENT_META: Record<string, { icon: string; color: string }> = {
  positive: { icon: "🙂", color: "var(--green)" },
  negative: { icon: "🙁", color: "var(--red)" },
  neutral:  { icon: "😐", color: "var(--muted)" },
  "no data": { icon: "🤷", color: "var(--muted)" },
};

export default function CoinDigestCard({ digest }: { digest: CoinDigest }) {
  const coin = digest.symbol.replace("/USDT", "");
  const sentiment = SENTIMENT_META[digest.sentiment_label || "no data"] ?? SENTIMENT_META["no data"];
  const change = digest.price_change_pct_24h;
  const watching = digest.watching_side && digest.watch_low !== null && digest.watch_high !== null;

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <CoinLogo symbol={digest.symbol} size={22} />
        <span style={{ fontWeight: 700, fontSize: 13 }}>{coin}</span>
        {change !== null && (
          <span style={{ color: pnlColor(change), fontSize: 12, fontWeight: 600, marginLeft: "auto" }}>{pct(change)}</span>
        )}
      </div>

      {digest.price_low_24h !== null && digest.price_high_24h !== null && (
        <div style={{ color: "var(--muted)", fontSize: 11 }}>
          24h range: {price4.format(digest.price_low_24h)} – {price4.format(digest.price_high_24h)}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span title={digest.sentiment_label ?? "no data"} style={{ fontSize: 13 }}>{sentiment.icon}</span>
        <span style={{ color: sentiment.color, fontSize: 11, fontWeight: 600 }}>
          News: {digest.sentiment_label === "no data" ? "unavailable" : digest.sentiment_label}
        </span>
      </div>

      {watching ? (
        <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 8px", fontSize: 11 }}>
          👀 Watching for a <b style={{ color: digest.watching_side === "long" ? "var(--green)" : "var(--red)" }}>{digest.watching_side?.toUpperCase()}</b> near {price4.format(digest.watch_low!)}–{price4.format(digest.watch_high!)}
        </div>
      ) : (
        <div style={{ color: "var(--muted)", fontSize: 11 }}>No active setup — just watching.</div>
      )}

      <div style={{ color: "var(--muted)", fontSize: 11, lineHeight: 1.4, paddingTop: 6, borderTop: "1px solid var(--border)" }}>
        {digest.summary}
      </div>
    </div>
  );
}
