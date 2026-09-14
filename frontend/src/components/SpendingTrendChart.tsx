import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "../api/client";
import { CHART } from "../lib/charts";
import { currency, currencyCompact, shortDate } from "../lib/format";
import { EmptyState } from "./ui";

export default function SpendingTrendChart({ data }: { data: TrendPoint[] }) {
  if (data.length === 0) {
    return <EmptyState>No history yet. Sync some transactions to see the trend.</EmptyState>;
  }
  return (
    <div className="chart chart-260">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }} barGap={2}>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis
            dataKey="period_start"
            tickFormatter={shortDate}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            minTickGap={20}
          />
          <YAxis
            tickFormatter={currencyCompact}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={54}
          />
          <Tooltip
            formatter={(v, name) => [currency(Number(v)), name === "income" ? "Income" : "Spent"]}
            labelFormatter={(l) => shortDate(String(l))}
            cursor={{ fill: "rgba(0,0,0,0.03)" }}
          />
          <Legend
            formatter={(v) => (v === "income" ? "Income" : "Spent")}
            iconType="circle"
            wrapperStyle={{ fontSize: 12 }}
          />
          <Bar dataKey="income" fill={CHART.positive} radius={[3, 3, 0, 0]} />
          <Bar dataKey="spent" fill={CHART.negative} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
