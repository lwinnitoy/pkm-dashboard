import { useEffect, useState } from "react";
import { api, type Holding, type InvestmentTransaction } from "../api/client";
import CategoryBreakdown from "../components/CategoryBreakdown";
import { Card, EmptyState, MetricTile } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { currency, shortDate } from "../lib/format";

function gainLoss(h: Holding): number | null {
  if (h.value == null || h.cost_basis == null) return null;
  return h.value - h.cost_basis;
}

export default function Investments() {
  const { portfolio } = useFinance();
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [txns, setTxns] = useState<InvestmentTransaction[]>([]);

  useEffect(() => {
    api.holdings().then(setHoldings).catch(() => setHoldings([]));
    api.investmentTransactions(50).then(setTxns).catch(() => setTxns([]));
  }, []);

  const linked = portfolio != null && portfolio.holdings_count > 0;

  if (!linked) {
    return (
      <Card title="Investments">
        <EmptyState>
          No investment accounts linked. Connect an investment institution (e.g. Wealthsimple)
          to see holdings, allocation, and portfolio value here.
        </EmptyState>
      </Card>
    );
  }

  // Reuse the category donut for allocation by mapping top holdings to slices.
  const allocation = (portfolio?.top_holdings ?? []).map((h) => ({
    category: h.ticker ?? h.security_name ?? "—",
    total: h.value,
    count: 0,
  }));

  return (
    <>
      <div className="grid grid-3">
        <Card>
          <MetricTile label="Portfolio value" value={currency(portfolio?.total_value)} />
        </Card>
        <Card>
          <MetricTile label="Holdings" value={String(portfolio?.holdings_count ?? 0)} />
        </Card>
        <Card>
          <MetricTile label="Accounts" value={String(portfolio?.by_account.length ?? 0)} />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Allocation" sub="Top holdings by value">
          <CategoryBreakdown data={allocation} />
        </Card>
        <Card title="By account">
          {(portfolio?.by_account ?? []).length === 0 ? (
            <EmptyState>No accounts.</EmptyState>
          ) : (
            <ul className="legend">
              {portfolio?.by_account.map((a) => (
                <li key={a.account_id}>
                  {a.account_name ?? "Account"}
                  <span className="legend-val">{currency(a.value)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Holdings">
        {holdings.length === 0 ? (
          <EmptyState>No holdings.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Holding</th>
                <th className="num">Qty</th>
                <th className="num">Price</th>
                <th className="num">Value</th>
                <th className="num">Gain / loss</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h, i) => {
                const gl = gainLoss(h);
                return (
                  <tr key={`${h.account_id}-${h.ticker ?? h.security_name ?? i}`}>
                    <td>
                      <span className="account-name">{h.ticker ?? "—"}</span>{" "}
                      <span className="muted">{h.security_name ?? ""}</span>
                    </td>
                    <td className="num">{h.quantity ?? "—"}</td>
                    <td className="num">{currency(h.price)}</td>
                    <td className="num">{currency(h.value)}</td>
                    <td className={`num ${gl == null ? "" : gl >= 0 ? "amt-in" : "amt-out"}`}>
                      {gl == null ? "—" : `${gl >= 0 ? "+" : ""}${currency(gl)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Investment activity">
        {txns.length === 0 ? (
          <EmptyState>No investment transactions.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Activity</th>
                <th>Type</th>
                <th className="num">Qty</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {txns.map((t) => (
                <tr key={t.id}>
                  <td className="muted">{shortDate(t.date)}</td>
                  <td>{t.name ?? t.ticker ?? "—"}</td>
                  <td>
                    <span className="tag">{t.subtype ?? t.type ?? "—"}</span>
                  </td>
                  <td className="num">{t.quantity ?? "—"}</td>
                  <td className="num">{currency(t.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
