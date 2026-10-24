import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  errorText,
  type Account,
  type CategoryComparison,
  type Goal,
  type GoalInput,
  type MerchantSpend,
  type NetWorthPoint,
  type PortfolioSummary,
  type SkippedItem,
  type Summary,
  type Transaction,
  type TrendPoint,
} from "../api/client";
import { FinanceContext, granularityFor } from "./financeContext";

/** "RBC: ITEM_LOGIN_REQUIRED; Wealthsimple: …" for a sync report. */
function describeSkipped(items: SkippedItem[]): string {
  return items.map((s) => `${s.institution}: ${s.error_code}`).join("; ");
}

/**
 * Fetches and shares all finance data across routed pages, driven by a single
 * global date range. Investments are optional (may be unlinked) so the portfolio
 * fetch is isolated and never breaks the rest of the dashboard.
 */
export function FinanceProvider({ children }: { children: React.ReactNode }) {
  const [range, setRange] = useState(180);
  const [loading, setLoading] = useState(true);
  // True once a refresh has succeeded. Until then pages would render empty data
  // as real zeros ("$0.00 spent", "No transactions yet"), so AppShell holds them.
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [trendGranularity, setTrendGranularity] = useState(granularityFor(180));
  const [merchants, setMerchants] = useState<MerchantSpend[]>([]);
  const [comparison, setComparison] = useState<CategoryComparison[]>([]);
  const [netWorth, setNetWorth] = useState<NetWorthPoint[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [categories, setCategories] = useState<string[]>([]);

  // Switching 30D → 1Y quickly starts two refreshes; only the newest may land,
  // or the topbar can say 1Y over 30-day numbers.
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++latest.current;
    setError(null);
    setLoading(true);
    const granularity = granularityFor(range);
    // Investments are optional, so a failure here mustn't fail the dashboard. But
    // they load with everything else: fetched afterwards, pages showed "no
    // investments linked" until the portfolio arrived. A failure is kept apart
    // from "not linked" (null), which would tell you to link what's linked.
    const portfolioP = api.investmentsPortfolio().then(
      (pf) => ({ pf, err: null }),
      (e: unknown) => ({ pf: null, err: errorText(e) }),
    );
    try {
      const [s, t, a, tr, m, c, nw, g, cats] = await Promise.all([
        api.summary(range),
        // Just enough for the Overview's "Recent transactions" card; the
        // Transactions page pages through full history on its own.
        api.transactions(6),
        api.accounts(),
        api.spendingTrend(range, granularity),
        api.topMerchants(range, 10),
        api.categoryComparison(range),
        api.netWorth(range),
        api.goals(),
        api.categories(),
      ]);
      const { pf, err } = await portfolioP;
      if (id !== latest.current) return;
      setSummary(s);
      setTransactions(t);
      setAccounts(a);
      setTrend(tr);
      setTrendGranularity(granularity);
      setMerchants(m);
      setComparison(c);
      setNetWorth(nw);
      setGoals(g);
      setCategories(cats);
      // On failure keep the last portfolio that did load, if any.
      if (err === null) setPortfolio(pf);
      setPortfolioError(err);
      setLoaded(true);
    } catch (e) {
      // Keep whatever was showing: stale numbers under an error beat zeros.
      if (id === latest.current) setError(errorText(e));
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const sync = useCallback(async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const r = await api.sync();
      // Investments live on a separate Plaid product, so a failure there must not
      // fail the transaction sync — but it does get reported, otherwise an item
      // that never consented to investments looks identical to one with no holdings.
      const inv = await api.investmentsSync().then(
        (res) => describeSkipped(res.skipped_details),
        (e: unknown) => `failed (${errorText(e)})`,
      );
      const banks = describeSkipped(r.skipped_details);
      const relogin = r.skipped_details.some((s) => s.error_code === "ITEM_LOGIN_REQUIRED");
      setMessage(
        `Synced: +${r.added} new, ${r.modified} updated, ${r.removed} removed.` +
          (banks ? ` Not synced: ${banks}.` : "") +
          (relogin ? " Reconnect that bank from Accounts." : "") +
          (inv ? ` Investments: ${inv}.` : ""),
      );
      await refresh();
    } catch (e) {
      setError(`Sync failed: ${errorText(e)}`);
    } finally {
      setSyncing(false);
    }
  }, [refresh]);

  const createGoal = useCallback(
    async (g: GoalInput) => {
      await api.createGoal(g);
      await refresh();
    },
    [refresh],
  );

  const deleteGoal = useCallback(
    async (id: number) => {
      await api.deleteGoal(id);
      await refresh();
    },
    [refresh],
  );

  return (
    <FinanceContext.Provider
      value={{
        loading,
        loaded,
        error,
        message,
        syncing,
        range,
        setRange,
        summary,
        transactions,
        accounts,
        trend,
        trendGranularity,
        merchants,
        comparison,
        netWorth,
        goals,
        portfolio,
        portfolioError,
        categories,
        refresh,
        sync,
        createGoal,
        deleteGoal,
      }}
    >
      {children}
    </FinanceContext.Provider>
  );
}
