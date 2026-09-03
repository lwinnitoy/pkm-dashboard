import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { CategorySpend } from "../api/client";
import { categoryColor } from "../lib/charts";
import { currency } from "../lib/format";
import { EmptyState } from "./ui";

export default function CategoryBreakdown({
  data,
  limit = 8,
}: {
  data: CategorySpend[];
  limit?: number;
}) {
  if (data.length === 0) return <EmptyState>No spending to break down yet.</EmptyState>;

  // Collapse the long tail into "Other" so the donut stays readable.
  const sorted = [...data].sort((a, b) => b.total - a.total);
  const head = sorted.slice(0, limit);
  const tail = sorted.slice(limit);
  const slices = [...head];
  if (tail.length > 0) {
    slices.push({
      category: "Other",
      total: tail.reduce((s, c) => s + c.total, 0),
      count: tail.reduce((s, c) => s + c.count, 0),
    });
  }
  const total = slices.reduce((s, c) => s + c.total, 0);

  return (
    <div className="grid grid-2" style={{ alignItems: "center" }}>
      <div className="chart chart-220">
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={slices}
              dataKey="total"
              nameKey="category"
              innerRadius="58%"
              outerRadius="88%"
              paddingAngle={1.5}
              stroke="none"
            >
              {slices.map((s, i) => (
                <Cell key={s.category} fill={categoryColor(i)} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => currency(Number(v))} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="legend">
        {slices.map((s, i) => (
          <li key={s.category}>
            <span className="dot" style={{ background: categoryColor(i) }} />
            {s.category}
            <span className="legend-val">
              {currency(s.total)}
              <span className="muted"> · {total ? Math.round((s.total / total) * 100) : 0}%</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
