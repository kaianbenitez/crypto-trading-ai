"use client";

export function Card({
  title, right, children, noPad, hoverable, className, style,
}: {
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  noPad?: boolean;
  hoverable?: boolean;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className={`ui-card${hoverable ? " ui-card--hoverable" : ""}${className ? ` ${className}` : ""}`}
      style={style}
    >
      {title && (
        <div className="ui-card__header">
          <span className="ui-card__title">{title}</span>
          {right}
        </div>
      )}
      <div className={noPad ? "" : "ui-card__body"}>{children}</div>
    </div>
  );
}

export default Card;
