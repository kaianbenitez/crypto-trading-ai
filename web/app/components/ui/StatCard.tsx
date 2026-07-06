import { Skeleton } from "./Skeleton";

export function StatCard({
  label, value, sub, color, loading, accent, large,
}: {
  label: string; value: string; sub?: string; color?: string; loading?: boolean; accent?: string; large?: boolean;
}) {
  return (
    <div
      className={`ui-stat-card${accent ? " ui-stat-card--accent" : ""}`}
      style={{ ["--stat-accent" as string]: accent, padding: large ? "20px 20px" : undefined }}
    >
      <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</div>
      {loading ? (
        <Skeleton h={large ? 32 : 24} />
      ) : (
        <div style={{ color: color || "var(--text)", fontSize: large ? "var(--text-2xl)" : "var(--text-xl)", fontWeight: 700, marginTop: 6, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>
          {value}
        </div>
      )}
      {sub && !loading && <div style={{ color: "var(--muted)", fontSize: "var(--text-2xs)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export default StatCard;
