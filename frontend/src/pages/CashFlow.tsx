import CashFlowSankey from "../components/CashFlowSankey";
import CategoryBreakdown from "../components/CategoryBreakdown";
import SpendingTrendChart from "../components/SpendingTrendChart";
import TopMerchants from "../components/TopMerchants";
import { Card, Delta, EmptyState, MetricTile } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { cashFlowTotals, savingsRate } from "../lib/derive";
import { currency, percent } from "../lib/format";

export default function CashFlow() {
  const { trend, summary, merchants, comparison } = useFinance();
  const { income, spending } = cashFlowTotals(trend);
  const rate = savingsRate(income, spending);
  const categories = summary?.by_category ?? [];

  return (
    <>
      <div className="grid grid-3">
        <Card>
          <MetricTile label="Income" value={currency(income)} />
        </Card>
        <Card>
          <MetricTile label="Spending" value={currency(spending)} />
        </Card>
        <Card>
          <MetricTile
            label="Net / savings rate"
            value={currency(income - spending)}
            foot={rate == null ? undefined : `${percent(rate)} of income`}
          />
        </Card>
      </div>

      <Card title="Where the money flows" sub="Income routed to spending categories and savings">
        <CashFlowSankey income={income} categories={categories} />
      </Card>

      <div className="grid grid-2">
        <Card title="Income vs spending over time">
          <SpendingTrendChart data={trend} />
        </Card>
        <Card title="Top merchants">
          <TopMerchants data={merchants} />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Spending by category">
          <CategoryBreakdown data={categories} />
        </Card>
        <Card title="vs previous period">
          {comparison.length === 0 ? (
            <EmptyState>Not enough history to compare periods yet.</EmptyState>
          ) : (
            <ul className="legend">
              {comparison.slice(0, 8).map((c) => (
                <li key={c.category}>
                  {c.category}
                  <span className="legend-val">
                    {currency(c.current)} <Delta value={c.pct_change} expense />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
