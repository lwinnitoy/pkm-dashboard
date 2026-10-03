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
import type { granularityFor } from "../data/financeContext";
import { CHART } from "../lib/charts";
import { parseDate } from "../lib/dates";
import { currency, currencyCompact, shortDate } from "../lib/format";
import { EmptyState } from "./ui";

type Granularity = ReturnType<typeof granularityFor>;

/**
 * Axis label for a bucket's `period_start`: the month name for monthly buckets
 * (with the year once the data crosses a calendar year), otherwise the bucket's
 * first day — the Monday, for weekly buckets.
 */
function tickLabel(periodStart: string, granularity: Granularity, withYear: boolean): string {
  if (granularity !== "month") return shortDate(periodStart);
  return parseDate(periodStart).toLocaleDateString("en-US", {
    month: "short",
    year: withYear ? "numeric" : undefined,
  });
}

/** Tooltip title: same buckets as the axis, spelled out so a week isn't read as a day. */
function tooltipLabel(periodStart: string, granularity: Granularity): string {
  if (granularity === "month") {
    return parseDate(periodStart).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  }
  if (granularity === "week") return `Week of ${shortDate(periodStart)}`;
  return shortDate(periodStart);
}

export default function SpendingTrendChart({
  data,
  granularity,
}: {
  data: TrendPoint[];
  granularity: Granularity;
}) {
  if (data.length === 0) {
    return <EmptyState>No history yet. Sync some transactions to see the trend.</EmptyState>;
  }
  const year = (p: TrendPoint) => parseDate(p.period_start).getFullYear();
  const withYear = year(data[0]) !== year(data[data.length - 1]);
  return (
    <div className="chart chart-260">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }} barGap={2}>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis
            dataKey="period_start"
            tickFormatter={(v) => tickLabel(String(v), granularity, withYear)}
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
            labelFormatter={(l) => tooltipLabel(String(l), granularity)}
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
