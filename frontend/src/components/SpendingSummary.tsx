import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Summary } from "../api/client";

export default function SpendingSummary({ summary }: { summary: Summary }) {
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
    </section>
  );
}
