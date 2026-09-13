import { Line, LineChart, ResponsiveContainer } from "recharts";
import { CHART } from "../lib/charts";

/** Card container with an optional header (title + sub + action slot). */
export function Card({
  title,
  sub,
  action,
  className = "",
  children,
}: {
  title?: string;
  sub?: string;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`card ${className}`.trim()}>
      {(title || action) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <div className="card-sub">{sub}</div>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** Labelled metric with an optional footnote / delta. */
export function MetricTile({
  label,
  value,
  foot,
  small = false,
}: {
  label: string;
  value: React.ReactNode;
  foot?: React.ReactNode;
  small?: boolean;
}) {
  return (
    <div className="metric-tile">
      <div className="metric-label">{label}</div>
      <div className={`metric-value${small ? " sm" : ""}`}>{value}</div>
      {foot && <div className="metric-foot">{foot}</div>}
    </div>
  );
}

/** Coloured percentage delta. `expense` inverts the color intent (up = bad). */
export function Delta({
  value,
  expense = false,
  label,
}: {
  value: number | null | undefined;
  expense?: boolean;
  label?: string;
}) {
  if (value == null) return null;
  const dir = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const arrow = value > 0 ? "▲" : value < 0 ? "▼" : "•";
  return (
    <span className={`delta ${dir}${expense ? " expense" : ""}`}>
      {arrow} {Math.abs(value).toFixed(1)}%{label ? ` ${label}` : ""}
    </span>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}

/** Tiny axis-less trend line for hero cards. */
export function Sparkline({
  data,
  dataKey,
  color = CHART.brand,
  height = 48,
}: {
  data: readonly object[];
  dataKey: string;
  color?: string;
  height?: number;
}) {
  if (data.length === 0) return null;
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={data as object[]} margin={{ top: 4, right: 2, bottom: 4, left: 2 }}>
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
