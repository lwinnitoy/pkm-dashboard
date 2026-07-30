import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "../api/client";

export default function SpendingTrendChart({ data }: { data: TrendPoint[] }) {
  return (
    <section className="card">
      <h2>Spending vs. income</h2>
      {data.length === 0 ? (
        <p className="muted">No history yet. Sync some transactions to see the trend.</p>
      ) : (
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period_start" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />
              <Legend />
              <Area
                type="monotone"
                dataKey="income"
                name="Income"
                stroke="#059669"
                fill="#05966933"
              />
              <Area
                type="monotone"
                dataKey="spent"
                name="Spent"
                stroke="#dc2626"
                fill="#dc262633"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
