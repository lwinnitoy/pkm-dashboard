import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { NetWorthPoint } from "../api/client";
import { CHART } from "../lib/charts";
import { currency, currencyCompact, shortDate } from "../lib/format";
import { EmptyState } from "./ui";

export default function NetWorthChart({ data }: { data: NetWorthPoint[] }) {
  if (data.length === 0) {
    return (
      <EmptyState>
        Net worth is tracked from daily balance snapshots — this chart fills in as they
        accrue (a snapshot is taken on each sync and once daily).
      </EmptyState>
    );
  }
  return (
    <div className="chart chart-260">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <defs>
            <linearGradient id="nwFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART.brand} stopOpacity={0.22} />
              <stop offset="100%" stopColor={CHART.brand} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            minTickGap={28}
          />
          <YAxis
            tickFormatter={currencyCompact}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={54}
          />
          <Tooltip
            formatter={(v) => [currency(Number(v)), "Net worth"]}
            labelFormatter={(l) => shortDate(String(l))}
          />
          <Area
            type="monotone"
            dataKey="net_worth"
            stroke={CHART.brand}
            strokeWidth={2}
            fill="url(#nwFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
