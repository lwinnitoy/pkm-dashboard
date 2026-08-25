import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PortfolioSummary } from "../api/client";

export default function FinancialOverview({
  spending,
  income,
  portfolio,
}: {
  spending: number;
  income: number;
  portfolio: PortfolioSummary | null;
}) {
  // The /portfolio endpoint always returns total_value (coalesced to 0.0), so we
  // key "no investments linked" off holdings_count — distinct from a linked-but-
  // empty portfolio — to show a connect prompt instead of a misleading $0.
  const hasInvestments = portfolio != null && portfolio.holdings_count > 0;
  const investments = portfolio?.total_value ?? 0;

  const chartData = [
    { name: "Spending", value: spending, fill: "#dc2626" },
    { name: "Income", value: income, fill: "#059669" },
    ...(hasInvestments
      ? [{ name: "Investments", value: investments, fill: "#4f46e5" }]
      : []),
  ];

  return (
    <section className="card">
      <h2>Overview</h2>
      <div className="overview-metrics">
        <div>
          <div className="metric-label">Spending</div>
          <div className="metric-value">${spending.toFixed(2)}</div>
        </div>
        <div>
          <div className="metric-label">Income</div>
          <div className="metric-value">${income.toFixed(2)}</div>
        </div>
        <div>
          <div className="metric-label">Investments</div>
          {hasInvestments ? (
            <div className="metric-value">${investments.toFixed(2)}</div>
          ) : (
            <div className="metric-value muted overview-connect">Connect investments</div>
          )}
        </div>
      </div>

      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
