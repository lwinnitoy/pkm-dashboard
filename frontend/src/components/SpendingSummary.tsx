import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CategoryComparison, Summary } from "../api/client";

export default function SpendingSummary({
  summary,
  comparison = [],
}: {
  summary: Summary;
  comparison?: CategoryComparison[];
}) {
  return (
    <section className="card">
      <div className="summary-head">
        <div>
          <div className="metric-label">Spent (last {summary.period_days} days)</div>
          <div className="metric-value">${summary.total_spent.toFixed(2)}</div>
        </div>
        <div>
          <div className="metric-label">Transactions</div>
          <div className="metric-value">{summary.transaction_count}</div>
        </div>
      </div>

      {summary.by_category.length > 0 && (
        <div style={{ width: "100%", height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={summary.by_category} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="category" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />
              <Bar dataKey="total" fill="#4f46e5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {comparison.length > 0 && (
        <div className="comparison">
          <div className="metric-label">vs. previous period</div>
          <ul className="comparison-list">
            {comparison.slice(0, 6).map((c) => (
              <li key={c.category}>
                <span>{c.category}</span>
                <span>
                  ${c.current.toFixed(0)}
                  {c.pct_change != null && (
                    <span className={c.pct_change > 0 ? "delta-up" : "delta-down"}>
                      {" "}
                      {c.pct_change > 0 ? "▲" : "▼"} {Math.abs(c.pct_change)}%
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
