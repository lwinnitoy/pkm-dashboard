import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { NetWorthPoint } from "../api/client";

export default function NetWorthChart({ data }: { data: NetWorthPoint[] }) {
  return (
    <section className="card">
      <h2>Net worth</h2>
      {data.length === 0 ? (
        <p className="muted">
          Net worth is tracked from daily balance snapshots — this chart fills in as
          they accrue (a snapshot is taken on each sync and once daily).
        </p>
      ) : (
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />
              <Line
                type="monotone"
                dataKey="net_worth"
                name="Net worth"
                stroke="#4f46e5"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
