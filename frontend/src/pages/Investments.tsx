import { useEffect, useState } from "react";
import { api, type Holding, type InvestmentTransaction } from "../api/client";
import CategoryBreakdown from "../components/CategoryBreakdown";
import { Card, Delta, EmptyState, MetricTile } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { currency, percent, shortDate } from "../lib/format";

/** A gain reads as a change, so it always carries its sign: +$12.30 / -$12.30. */
function signedCurrency(n: number): string {
  return `${n >= 0 ? "+" : ""}${currency(n)}`;
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

// How a holding was priced when the institution's own price was missing — Plaid
// reports 0 for every Wealthsimple holding.
const BORROWED_PRICE: Record<string, { label: string; title: string }> = {
  close_price: {
    label: "last close",
    title: "No price from the institution, so this uses the security's last close.",
  },
  transaction: {
    label: "last trade",
    title: "No price from the institution, so this uses the account's latest buy or sell.",
  },
};

function PriceHint({ h }: { h: Holding }) {
  const borrowed = h.price_source ? BORROWED_PRICE[h.price_source] : undefined;
  if (!borrowed) return null;
  return (
    <div className="cell-hint" title={borrowed.title}>
      {borrowed.label}
      {h.price_as_of ? ` · ${shortDate(h.price_as_of)}` : ""}
    </div>
  );
}

export default function Investments() {
  const { portfolio, loading } = useFinance();
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [txns, setTxns] = useState<InvestmentTransaction[]>([]);

  useEffect(() => {
    api.holdings().then(setHoldings).catch(() => setHoldings([]));
    api.investmentTransactions(50).then(setTxns).catch(() => setTxns([]));
  }, []);

  // total_value is null exactly when nothing is linked (the seam's contract), so
  // an investment account whose holdings haven't synced yet still shows here.
  if (loading && portfolio == null) {
    return (
      <Card title="Investments">
        <EmptyState>Loading…</EmptyState>
      </Card>
    );
  }
  if (portfolio == null || portfolio.total_value == null) {
    return (
      <Card title="Investments">
        <EmptyState>
          No investment accounts linked. Connect an investment institution (e.g. Wealthsimple)
          to see holdings, allocation, and portfolio value here.
        </EmptyState>
      </Card>
    );
  }

  const gain = portfolio.unrealized_gain;

  // Reuse the category donut for allocation by mapping slices onto it.
  const allocation = portfolio.allocation.map((s) => ({
    category: s.ticker ?? s.security_name ?? "—",
    total: s.amount,
    count: 0,
  }));

  return (
    <>
      <div className="grid grid-3">
        <Card>
          <MetricTile
            label="Portfolio value"
            value={currency(portfolio.total_value)}
            foot={`${plural(portfolio.holdings_count, "holding")} · ${plural(
              portfolio.by_account.length,
              "account",
            )}`}
          />
        </Card>
        <Card>
          <MetricTile
            label="Unrealized gain"
            value={gain == null ? "—" : signedCurrency(gain)}
            foot={
              <>
                <Delta value={portfolio.unrealized_gain_pct} /> vs. cost basis, including any
                cash held
              </>
            }
          />
        </Card>
        <Card>
          <MetricTile
            label="Cost basis"
            value={currency(portfolio.cost_basis)}
            foot="What you paid for current holdings"
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card
          title="Allocation"
          sub={
            portfolio.allocation_basis === "market_value"
              ? "By market value"
              : "By cost basis — per-holding prices unavailable"
          }
        >
          {allocation.length === 0 ? (
            <EmptyState>No holdings to allocate.</EmptyState>
          ) : (
            <CategoryBreakdown data={allocation} />
          )}
        </Card>
        <Card title="By account">
          {portfolio.by_account.length === 0 ? (
            <EmptyState>No accounts.</EmptyState>
          ) : (
            <ul className="legend">
              {portfolio.by_account.map((a) => (
                <li key={a.account_id}>
                  {a.account_name ?? "Account"}
                  <span className="legend-val">{currency(a.value)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card
        title="Holdings"
        sub={
          portfolio.unpriced_count > 0
            ? `${portfolio.unpriced_count} of ${portfolio.holdings_count} without a current price`
            : undefined
        }
      >
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
                <th className="num">Cost</th>
                <th className="num">Gain / loss</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h, i) => (
                <tr key={`${h.account_id}-${h.ticker ?? h.security_name ?? i}`}>
                  <td>
                    <span className="account-name">{h.ticker ?? "—"}</span>{" "}
                    <span className="muted">{h.security_name ?? ""}</span>
                  </td>
                  <td className="num">{h.quantity ?? "—"}</td>
                  <td className="num">
                    {currency(h.price)}
                    <PriceHint h={h} />
                  </td>
                  <td className="num">{currency(h.value)}</td>
                  <td className="num">{currency(h.cost_basis)}</td>
                  <td
                    className={`num ${h.gain == null ? "" : h.gain >= 0 ? "amt-in" : "amt-out"}`}
                  >
                    {h.gain == null ? "—" : signedCurrency(h.gain)}
                    {h.gain_pct != null && (
                      <div className="cell-hint">{percent(h.gain_pct, true)}</div>
                    )}
                  </td>
                </tr>
              ))}
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
              {txns.map((t) => {
                // Plaid: negative = cash credited to the account (e.g. a dividend).
                const moneyIn = t.amount != null && t.amount < 0;
                return (
                  <tr key={t.id}>
                    <td className="muted">{shortDate(t.date)}</td>
                    <td>{t.name ?? t.ticker ?? "—"}</td>
                    <td>
                      <span className="tag">{t.subtype ?? t.type ?? "—"}</span>
                    </td>
                    <td className="num">{t.quantity ?? "—"}</td>
                    <td
                      className={`num ${t.amount == null ? "" : moneyIn ? "amt-in" : "amt-out"}`}
                    >
                      {t.amount == null ? "—" : `${moneyIn ? "+" : ""}${currency(Math.abs(t.amount))}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
