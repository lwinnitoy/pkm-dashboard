import { useEffect, useState } from "react";
import { api, errorText, type Holding, type InvestmentTransaction } from "../api/client";
import CategoryBreakdown from "../components/CategoryBreakdown";
import { Card, Delta, EmptyState, MetricTile } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { currency, percent, shortDate } from "../lib/format";

/** A gain reads as a change, so it always carries its sign: +$12.30 / -$12.30. */
function signedCurrency(n: number, code?: string | null): string {
  return `${n >= 0 ? "+" : ""}${currency(n, code)}`;
}

/** A list fetched by this page: null while loading, or why it failed. */
type Loaded<T> = { rows: T[] | null; error: string | null };

function useList<T>(fetch: () => Promise<T[]>): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ rows: null, error: null });
  useEffect(() => {
    let live = true;
    fetch().then(
      (rows) => live && setState({ rows, error: null }),
      (e: unknown) => live && setState({ rows: null, error: errorText(e) }),
    );
    return () => {
      live = false;
    };
  }, [fetch]);
  return state;
}

/** The loading / failed / empty message for a list, or null to render the rows. */
function listState<T>({ rows, error }: Loaded<T>, what: string): string | null {
  if (error) return `Couldn't load ${what}: ${error}`;
  if (rows == null) return "Loading…";
  if (rows.length === 0) return `No ${what}.`;
  return null;
}

const fetchHoldings = () => api.holdings();
const fetchActivity = () => api.investmentTransactions(50);

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
  const { portfolio, portfolioError, loading } = useFinance();
  const holdingsList = useList<Holding>(fetchHoldings);
  const activityList = useList<InvestmentTransaction>(fetchActivity);
  const holdings = holdingsList.rows ?? [];
  const txns = activityList.rows ?? [];
  const holdingsEmpty = listState(holdingsList, "holdings");
  const activityEmpty = listState(activityList, "investment transactions");

  // total_value is null exactly when nothing is linked (the seam's contract), so
  // an investment account whose holdings haven't synced yet still shows here.
  if (loading && portfolio == null) {
    return (
      <Card title="Investments">
        <EmptyState>Loading…</EmptyState>
      </Card>
    );
  }
  if (portfolio == null && portfolioError) {
    return (
      <Card title="Investments">
        <EmptyState>Couldn't load investments: {portfolioError}</EmptyState>
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
        {holdingsEmpty ? (
          <EmptyState>{holdingsEmpty}</EmptyState>
        ) : (
          <div className="table-wrap">
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
                      {currency(h.price, h.currency)}
                      <PriceHint h={h} />
                    </td>
                    <td className="num">{currency(h.value, h.currency)}</td>
                    <td className="num">{currency(h.cost_basis, h.currency)}</td>
                    <td
                      className={`num ${h.gain == null ? "" : h.gain >= 0 ? "amt-in" : "amt-out"}`}
                    >
                      {h.gain == null ? "—" : signedCurrency(h.gain, h.currency)}
                      {h.gain_pct != null && (
                        <div className="cell-hint">{percent(h.gain_pct, true)}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Investment activity">
        {activityEmpty ? (
          <EmptyState>{activityEmpty}</EmptyState>
        ) : (
          <div className="table-wrap">
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
                        {t.amount == null ? "—" : `${moneyIn ? "+" : ""}${currency(Math.abs(t.amount), t.currency)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
