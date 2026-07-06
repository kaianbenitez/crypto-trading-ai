export function Badge({ children, color, bg }: { children: React.ReactNode; color?: string; bg?: string }) {
  const c = color || "var(--muted)";
  return (
    <span
      className="ui-badge"
      style={{ color: c, background: bg || `color-mix(in oklab, ${c} 16%, transparent)`, borderColor: `color-mix(in oklab, ${c} 32%, transparent)` }}
    >
      {children}
    </span>
  );
}

export default Badge;
