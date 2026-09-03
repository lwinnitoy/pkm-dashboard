import { Link } from "react-router-dom";
import CategoryBreakdown from "../components/CategoryBreakdown";
import TransactionsTable from "../components/TransactionsTable";
import { Card, Delta, EmptyState, MetricTile, Sparkline } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { cashFlowTotals, netWorthChange, savingsRate } from "../lib/derive";
import { currency, currencyWhole, percent } from "../lib/format";

export default function Overview() {
  const { netWorth, trend, summary, transactions, portfolio } = useFinance();

  const nw = netWorthChange(netWorth);
  const { income, spending } = cashFlowTotals(trend);
  const rate = savingsRate(income, spending);
  const invested = portfolio && portfolio.holdings_count > 0 ? portfolio.total_value : null;

  return (
    <>
      <div className="grid grid-3">
        <Card className="span-2">
          <div className="hero">
            <div className="metric-label">Net worth</div>
            <div className="metric-value">{nw ? currencyWhole(nw.latest) : "—"}</div>
            {nw && (
              <div>
                <Delta value={nw.changePct} />{" "}
                <span className="muted">{currency(nw.changeAbs)} over range</span>
              </div>
            )}
          </div>
          {netWorth.length > 0 ? (
            <Sparkline data={netWorth} dataKey="net_worth" height={64} />
          ) : (
            <EmptyState>Net-worth history accrues as balance snapshots are taken.</EmptyState>
          )}
        </Card>

        <Card title="Investments">
          {invested != null ? (
            <MetricTile
              label="Portfolio value"
              value={currencyWhole(invested)}
              foot={`${portfolio?.holdings_count} holdings`}
            />
          ) : (
            <EmptyState>
              No investments linked. <Link to="/accounts">Connect an account</Link>.
            </EmptyState>
          )}
        </Card>
      </div>

      <div className="grid grid-3">
        <Card>
          <MetricTile label="Income" value={currency(income)} foot="money in, this range" />
        </Card>
        <Card>
          <MetricTile label="Spending" value={currency(spending)} foot="money out, this range" />
        </Card>
        <Card>
          <MetricTile
            label="Savings rate"
            value={rate == null ? "—" : percent(rate)}
            foot={`${currency(income - spending)} kept`}
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Spending by category">
          <CategoryBreakdown data={summary?.by_category ?? []} />
        </Card>
        <Card title="Recent transactions" action={<Link className="card-sub" to="/transactions">View all</Link>}>
          <TransactionsTable transactions={transactions.slice(0, 6)} />
        </Card>
      </div>
    </>
  );
}
