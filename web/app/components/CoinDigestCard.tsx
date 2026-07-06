import { Smiley, SmileySad, SmileyMeh, Question, Eye } from "@phosphor-icons/react";
import { CoinDigest } from "@/lib/api";
import { pct, pnlColor, price4 } from "@/lib/format";
import CoinLogo from "./CoinLogo";

const SENTIMENT_META: Record<string, { Icon: typeof Smiley; color: string }> = {
  positive:  { Icon: Smiley,    color: "var(--green)" },
  negative:  { Icon: SmileySad, color: "var(--red)"    },
  neutral:   { Icon: SmileyMeh, color: "var(--muted)"  },
  "no data": { Icon: Question,  color: "var(--muted)"  },
};

export default function CoinDigestCard({ digest }: { digest: CoinDigest }) {
  const coin = digest.symbol.replace("/USDT", "");
  const sentiment = SENTIMENT_META[digest.sentiment_label || "no data"] ?? SENTIMENT_META["no data"];
  const SentimentIcon = sentiment.Icon;
  const change = digest.price_change_pct_24h;
  const watching = digest.watching_side && digest.watch_low !== null && digest.watch_high !== null;

  return (
    <div className="ui-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <CoinLogo symbol={digest.symbol} size={22} />
        <span style={{ fontWeight: 700, fontSize: "var(--text-sm)" }}>{coin}</span>
        {change !== null && (
          <span style={{ color: pnlColor(change), fontSize: "var(--text-xs)", fontWeight: 600, marginLeft: "auto" }}>{pct(change)}</span>
        )}
      </div>

      {digest.price_low_24h !== null && digest.price_high_24h !== null && (
        <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>
          24h range: {price4.format(digest.price_low_24h)} – {price4.format(digest.price_high_24h)}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span title={digest.sentiment_label ?? "no data"} style={{ display: "inline-flex" }}>
          <SentimentIcon size={15} weight="fill" color={sentiment.color} />
        </span>
        <span style={{ color: sentiment.color, fontSize: "var(--text-2xs)", fontWeight: 600 }}>
          News: {digest.sentiment_label === "no data" ? "unavailable" : digest.sentiment_label}
        </span>
      </div>

      {watching ? (
        <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "6px 8px", fontSize: "var(--text-2xs)", display: "flex", alignItems: "flex-start", gap: 6 }}>
          <Eye size={13} style={{ flexShrink: 0, marginTop: 1, color: "var(--muted)" }} />
          <span>Watching for a <b style={{ color: digest.watching_side === "long" ? "var(--green)" : "var(--red)" }}>{digest.watching_side?.toUpperCase()}</b> near {price4.format(digest.watch_low!)}–{price4.format(digest.watch_high!)}</span>
        </div>
      ) : (
        <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)" }}>No active setup — just watching.</div>
      )}

      <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", lineHeight: 1.4, paddingTop: 6, borderTop: "1px solid var(--border)" }}>
        {digest.summary}
      </div>
    </div>
  );
}
